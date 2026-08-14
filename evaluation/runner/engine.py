from __future__ import annotations

import csv
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from mcp_ops_ai_agent.engineering_rag import EngineeringRagService
from mcp_ops_ai_agent.tool_discovery.embeddings import embedding_provider_from_settings
from mcp_ops_ai_agent.tool_discovery.models import (
    ToolDiscoveryResponse,
    ToolDiscoveryResult,
)
from mcp_ops_ai_agent.tool_discovery.retrieval import explanation
from mcp_ops_ai_agent.tool_discovery.service import ToolDiscoveryService
from mcp_ops_ai_agent.workflows.models import WorkflowPlanRequest
from mcp_ops_ai_agent.workflows.planner import PlannerOutputError, workflow_planner_from_settings
from mcp_ops_ai_agent.workflows.service import WorkflowPlanningService
from mcp_ops_ai_agent.workflows.validator import WorkflowValidationError
from mcp_ops_common.config import get_settings
from mcp_ops_observability.metrics import record_ai_evaluation_summary

from evaluation.datasets.synthetic import BenchmarkItem, generate_benchmark_items
from evaluation.metrics.core import MetricInputs, compute_summary
from evaluation.reports.markdown import render_markdown_report
from evaluation.scenarios.configs import EvaluationConfig, evaluation_configs

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "datasets" / "engineering_tasks.json"
HELDOUT_ADVERSARIAL_PATH = ROOT / "datasets" / "heldout_adversarial_engineering_tasks.json"
RESULTS_DIR = ROOT / "results"
REPORT_PATH = ROOT / "reports" / "latest.md"
CSV_PATH = RESULTS_DIR / "latest.csv"


@dataclass(frozen=True, slots=True)
class EvaluationCaseResult:
    id: str
    category: str
    config: str
    request: str
    expected_tools: list[str]
    actual_tools: list[str]
    prohibited_tools: list[str]
    required_approvals: list[str]
    actual_approvals: list[str]
    relevant_documents: list[str]
    retrieved_documents: list[str]
    workflow_valid: bool
    workflow_completed: bool
    execution_succeeded: bool
    planner_latency_ms: float
    end_to_end_latency_ms: float
    token_usage: int
    estimated_cost_usd: float | None
    planner_provider: str
    planner_model: str
    embedding_provider: str
    embedding_fallback_allowed: bool
    retrieval_backend: str
    error_stage: str | None = None
    error_type: str | None = None
    error_reason: str | None = None
    attempts: int = 1
    finish_reason: str | None = None
    retry_attempted: bool = False
    retry_failure_reason: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class EvaluationRunResult:
    mode: str
    generated_at: str
    dataset_path: str
    summaries: list[dict[str, Any]]
    cases: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class _EvaluationRuntime:
    service: WorkflowPlanningService
    planner_provider: str
    planner_model: str
    embedding_provider: str
    embedding_fallback_allowed: bool
    retrieval_backend: str


class AllToolsDiscovery:
    def __init__(self, wrapped: ToolDiscoveryService) -> None:
        self.wrapped = wrapped
        self.documents = wrapped.documents
        self.index = wrapped.index

    def retrieve(
        self,
        query: str,
        *,
        role: str = "ENGINEER",
        top_k: int = 50,
        minimum_score: float = 0.0,
        allowed_servers: set[str] | None = None,
        allowed_categories: set[str] | None = None,
    ) -> ToolDiscoveryResponse:
        del top_k, minimum_score, allowed_servers, allowed_categories
        ranked: list[ToolDiscoveryResult] = []
        for document in self.documents:
            if document.required_roles and role.upper() not in {
                item.upper() for item in document.required_roles
            }:
                continue
            ranked.append(
                ToolDiscoveryResult(
                    tool=document,
                    semantic_score=1.0,
                    lexical_score=1.0,
                    combined_score=1.0,
                    authorization_status="authorized",
                    explanation=explanation(query, document),
                )
            )
        return ToolDiscoveryResponse(
            query=query,
            role=role,
            ranked_tools=ranked,
            filtered_out_unauthorized=0,
            index_backend="all-tools",
        )


def run_evaluation(
    *,
    selected_configs: tuple[EvaluationConfig, ...] | None = None,
    limit: int | None = None,
    output: bool = True,
    mode: str = "mock",
    dataset_name: str = "synthetic",
) -> EvaluationRunResult:
    dataset = _load_dataset(dataset_name)
    dataset_path = _dataset_path(dataset_name)
    if limit is not None:
        dataset = dataset[:limit]
    configs = selected_configs or evaluation_configs()
    DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if dataset_name == "synthetic":
        DATASET_PATH.write_text(
            json.dumps([item.as_payload() for item in dataset], indent=2),
            encoding="utf-8",
        )

    case_results: list[EvaluationCaseResult] = []
    summaries: list[dict[str, Any]] = []
    for config in configs:
        metric_inputs: list[MetricInputs] = []
        runtime_error: Exception | None = None
        runtime: _EvaluationRuntime | None = None
        try:
            runtime = _build_runtime(config, mode=mode)
        except Exception as exc:  # noqa: BLE001 - configuration failures are benchmark data.
            runtime_error = exc
        for item in dataset:
            if runtime is None:
                case_result, metric_input = _failed_case_result(
                    item,
                    config,
                    mode=mode,
                    error=runtime_error or RuntimeError("evaluation runtime unavailable"),
                )
            else:
                case_result, metric_input = _evaluate_case(
                    item,
                    config,
                    mode=mode,
                    runtime=runtime,
                )
            case_results.append(case_result)
            metric_inputs.append(metric_input)
        summary = compute_summary(config=config.name, mode=mode, inputs=metric_inputs)
        summaries.append(summary.as_payload())
        record_ai_evaluation_summary(config=config.name, mode=mode, metrics=summary.as_payload())

    payload = EvaluationRunResult(
        mode=mode,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        dataset_path=str(dataset_path),
        summaries=summaries,
        cases=[asdict(result) for result in case_results],
    )
    if output:
        _write_outputs(payload)
    return payload


def _build_runtime(config: EvaluationConfig, *, mode: str) -> _EvaluationRuntime:
    settings = get_settings()
    fallback_allowed = mode != "real"
    embedding_provider_name = settings.embedding_provider.lower()
    embedding_provider = embedding_provider_from_settings(
        settings,
        allow_fallback=fallback_allowed,
    )
    base_discovery = ToolDiscoveryService(embedding_provider=embedding_provider, settings=settings)
    discovery = AllToolsDiscovery(base_discovery) if config.use_all_tools else base_discovery
    planner = (
        workflow_planner_from_settings(settings, allow_fallback=False)
        if mode == "real"
        else None
    )
    service = WorkflowPlanningService(
        discovery=cast(ToolDiscoveryService, discovery),
        rag=EngineeringRagService(embedding_provider=embedding_provider, settings=settings),
        planner=planner,
        use_rag=config.use_rag,
        use_capability_graph=config.use_capability_graph,
    )
    return _EvaluationRuntime(
        service=service,
        planner_provider=planner.planner_provider if planner is not None else "deterministic",
        planner_model=(
            planner.planner_model
            if planner is not None
            else "deterministic-workflow-planner-v1"
        ),
        embedding_provider=embedding_provider_name,
        embedding_fallback_allowed=fallback_allowed,
        retrieval_backend=(
            "all-tools" if config.use_all_tools else base_discovery.index.backend_name
        ),
    )


def _load_dataset(dataset_name: str) -> list[BenchmarkItem]:
    if dataset_name == "synthetic":
        return generate_benchmark_items()
    if dataset_name == "heldout_adversarial":
        raw_items = json.loads(HELDOUT_ADVERSARIAL_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw_items, list):
            raise ValueError("Held-out adversarial dataset must be a list.")
        return [_heldout_item(item) for item in raw_items]
    raise ValueError(f"Unknown evaluation dataset: {dataset_name}.")


def _dataset_path(dataset_name: str) -> Path:
    if dataset_name == "synthetic":
        return DATASET_PATH
    if dataset_name == "heldout_adversarial":
        return HELDOUT_ADVERSARIAL_PATH
    raise ValueError(f"Unknown evaluation dataset: {dataset_name}.")


def _heldout_item(payload: object) -> BenchmarkItem:
    if not isinstance(payload, dict):
        raise ValueError("Held-out adversarial item must be an object.")
    expected_resources = _string_list(payload.get("expected_resources"))
    return BenchmarkItem(
        id=_required_string(payload, "id"),
        category="heldout adversarial",
        request=_required_string(payload, "request"),
        role=str(payload.get("role") or "ENGINEER"),
        environment=str(
            payload.get("environment") or _environment_from_resources(expected_resources)
        ),
        expected_tools=_string_list(payload.get("expected_tools")),
        acceptable_tools=_string_list(payload.get("acceptable_tools")),
        prohibited_tools=_string_list(payload.get("prohibited_tools")),
        required_approvals=_string_list(payload.get("required_approvals")),
        expected_resources=expected_resources,
        relevant_documents=_string_list(payload.get("relevant_documents")),
        expected_outcome=_required_string(payload, "expected_outcome"),
    )


def _required_string(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Held-out adversarial item is missing {field_name}.")
    return value


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _environment_from_resources(resources: list[str]) -> str:
    lowered = " ".join(resources).lower()
    if "production" in lowered:
        return "production"
    if "staging" in lowered:
        return "staging"
    return "dev"


def _evaluate_case(
    item: BenchmarkItem,
    config: EvaluationConfig,
    *,
    mode: str,
    runtime: _EvaluationRuntime,
) -> tuple[EvaluationCaseResult, MetricInputs]:
    started = time.perf_counter()
    fallback_allowed = runtime.embedding_fallback_allowed
    embedding_provider_name = runtime.embedding_provider
    planner_provider = runtime.planner_provider
    planner_model = runtime.planner_model
    retrieval_backend = runtime.retrieval_backend
    actual_tools: list[str] = []
    actual_approvals: list[str] = []
    retrieved_documents: list[str] = []
    workflow_valid = False
    error: str | None = None
    error_stage: str | None = None
    error_type: str | None = None
    error_reason: str | None = None
    attempts = 1
    finish_reason: str | None = None
    retry_attempted = False
    retry_failure_reason: str | None = None
    provider_success = True
    unknown_or_disallowed_tools = 0
    planner_started = time.perf_counter()
    try:
        result = runtime.service.plan(
            WorkflowPlanRequest(
                user_request=item.request,
                role=item.role,
                created_by="evaluation-runner",
                target_environment=item.environment,
                top_k=50 if config.use_all_tools else 12,
            )
        )
        workflow_valid = result.ok
        planner_provider = result.planner_provider
        planner_model = result.workflow.planner_model
        retrieval_backend = result.retrieval_backend
        if result.discovered_tools:
            retrieval_backend = str(
                result.discovered_tools[0].get("index_backend", retrieval_backend)
            )
        actual_tools = [node.tool_name for node in result.workflow.nodes]
        actual_approvals = [
            node.tool_name for node in result.workflow.nodes if node.approval_required
        ]
        retrieved_documents = [
            str(entry["citation_id"]) for entry in result.retrieved_knowledge
        ]
    except WorkflowValidationError as exc:
        error = "; ".join(issue.code for issue in exc.issues)
        error_stage = "workflow_validation"
        error_type = exc.__class__.__name__
        error_reason = "; ".join(
            f"{issue.code}: {issue.message}" for issue in exc.issues[:3]
        )
        unknown_or_disallowed_tools = sum(
            1
            for issue in exc.issues
            if issue.code in {"unknown_tool", "tool_not_discovered"}
        )
    except PlannerOutputError as exc:
        error = exc.__class__.__name__
        error_stage = exc.stage
        error_type = exc.__class__.__name__
        error_reason = exc.reason
        attempts = exc.attempt
        finish_reason = exc.finish_reason
        retry_attempted = exc.retry_attempted
        retry_failure_reason = exc.retry_failure_reason
        provider_success = not exc.stage.startswith("provider_")
    except Exception as exc:  # noqa: BLE001 - evaluation records failures as data
        error = exc.__class__.__name__
        error_stage = "runtime"
        error_type = exc.__class__.__name__
        error_reason = str(exc)[:500] or exc.__class__.__name__
    planner_latency_ms = (time.perf_counter() - planner_started) * 1000
    e2e_latency_ms = (time.perf_counter() - started) * 1000
    prohibited_attempted = bool(set(actual_tools) & set(item.prohibited_tools))
    approvals_correct = set(actual_approvals) == set(item.required_approvals)
    workflow_completed = workflow_valid and not prohibited_attempted and approvals_correct
    token_usage = 0 if mode == "mock" else _estimate_tokens(item.request, actual_tools)
    cost = None if mode == "mock" else round(token_usage * 0.000002, 6)
    case_result = EvaluationCaseResult(
        id=item.id,
        category=item.category,
        config=config.name,
        request=item.request,
        expected_tools=item.expected_tools,
        actual_tools=actual_tools,
        prohibited_tools=item.prohibited_tools,
        required_approvals=item.required_approvals,
        actual_approvals=actual_approvals,
        relevant_documents=item.relevant_documents,
        retrieved_documents=retrieved_documents,
        workflow_valid=workflow_valid,
        workflow_completed=workflow_completed,
        execution_succeeded=workflow_completed,
        planner_latency_ms=round(planner_latency_ms, 4),
        end_to_end_latency_ms=round(e2e_latency_ms, 4),
        token_usage=token_usage,
        estimated_cost_usd=cost,
        planner_provider=planner_provider,
        planner_model=planner_model,
        embedding_provider=embedding_provider_name,
        embedding_fallback_allowed=fallback_allowed,
        retrieval_backend=retrieval_backend,
        error_stage=error_stage,
        error_type=error_type,
        error_reason=error_reason,
        attempts=attempts,
        finish_reason=finish_reason,
        retry_attempted=retry_attempted,
        retry_failure_reason=retry_failure_reason,
        error=error,
    )
    metric_input = MetricInputs(
        expected_tools=item.expected_tools,
        acceptable_tools=item.acceptable_tools,
        actual_tools=actual_tools,
        prohibited_tools=item.prohibited_tools,
        required_approvals=item.required_approvals,
        actual_approvals=actual_approvals,
        relevant_documents=item.relevant_documents,
        retrieved_documents=retrieved_documents,
        workflow_valid=workflow_valid,
        workflow_completed=workflow_completed,
        execution_succeeded=workflow_completed,
        planner_latency_ms=planner_latency_ms,
        end_to_end_latency_ms=e2e_latency_ms,
        token_usage=token_usage,
        estimated_cost_usd=cost,
        provider_success=provider_success,
        unknown_or_disallowed_tools=unknown_or_disallowed_tools,
    )
    return case_result, metric_input


def _failed_case_result(
    item: BenchmarkItem,
    config: EvaluationConfig,
    *,
    mode: str,
    error: Exception,
) -> tuple[EvaluationCaseResult, MetricInputs]:
    error_name = error.__class__.__name__
    error_reason = str(error)[:500] or error_name
    case_result = EvaluationCaseResult(
        id=item.id,
        category=item.category,
        config=config.name,
        request=item.request,
        expected_tools=item.expected_tools,
        actual_tools=[],
        prohibited_tools=item.prohibited_tools,
        required_approvals=item.required_approvals,
        actual_approvals=[],
        relevant_documents=item.relevant_documents,
        retrieved_documents=[],
        workflow_valid=False,
        workflow_completed=False,
        execution_succeeded=False,
        planner_latency_ms=0.0,
        end_to_end_latency_ms=0.0,
        token_usage=0,
        estimated_cost_usd=None,
        planner_provider="unavailable",
        planner_model="unavailable",
        embedding_provider=get_settings().embedding_provider.lower(),
        embedding_fallback_allowed=mode != "real",
        retrieval_backend="unavailable",
        error_stage="runtime_setup",
        error_type=error_name,
        error_reason=error_reason,
        attempts=1,
        finish_reason=None,
        retry_attempted=False,
        retry_failure_reason=None,
        error=error_name,
    )
    metric_input = MetricInputs(
        expected_tools=item.expected_tools,
        acceptable_tools=item.acceptable_tools,
        actual_tools=[],
        prohibited_tools=item.prohibited_tools,
        required_approvals=item.required_approvals,
        actual_approvals=[],
        relevant_documents=item.relevant_documents,
        retrieved_documents=[],
        workflow_valid=False,
        workflow_completed=False,
        execution_succeeded=False,
        planner_latency_ms=0.0,
        end_to_end_latency_ms=0.0,
        token_usage=0,
        estimated_cost_usd=None,
        provider_success=False,
        unknown_or_disallowed_tools=0,
    )
    return case_result, metric_input


def _write_outputs(payload: EvaluationRunResult) -> None:
    latest_json = RESULTS_DIR / "latest.json"
    latest_json.write_text(json.dumps(asdict(payload), indent=2), encoding="utf-8")
    timestamp = payload.generated_at.replace(":", "").replace("-", "")
    timestamped_json = RESULTS_DIR / f"{timestamp}.json"
    timestamped_json.write_text(json.dumps(asdict(payload), indent=2), encoding="utf-8")
    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "config",
                "cases",
                "provider_successful_cases",
                "provider_failed_cases",
                "provider_success_rate",
                "tool_recall",
                "tool_precision",
                "exact_tool_set_accuracy",
                "workflow_validity_rate",
                "workflow_completion_rate",
                "benchmark_unexpected_tool_rate",
                "unknown_or_disallowed_tool_rate",
                "policy_violation_attempt_rate",
                "approval_classification_accuracy",
                "rag_recall_at_k",
                "rag_mrr",
                "average_workflow_length",
                "end_to_end_workflow_validity_rate",
                "end_to_end_execution_success_rate",
                "planner_latency_ms",
                "end_to_end_latency_ms",
                "mode",
            ],
        )
        writer.writeheader()
        for summary in payload.summaries:
            writer.writerow({key: summary.get(key) for key in writer.fieldnames})
    REPORT_PATH.write_text(render_markdown_report(payload), encoding="utf-8")


def _estimate_tokens(request: str, tools: list[str]) -> int:
    return max(1, len(request.split()) + len(tools) * 24)
