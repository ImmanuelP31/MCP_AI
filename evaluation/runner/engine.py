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
from mcp_ops_ai_agent.workflows.planner import workflow_planner_from_settings
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
    embedding_provider: str
    embedding_fallback_allowed: bool
    error: str | None = None


@dataclass(frozen=True, slots=True)
class EvaluationRunResult:
    mode: str
    generated_at: str
    dataset_path: str
    summaries: list[dict[str, Any]]
    cases: list[dict[str, Any]]


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
) -> EvaluationRunResult:
    dataset = generate_benchmark_items()
    if limit is not None:
        dataset = dataset[:limit]
    configs = selected_configs or evaluation_configs()
    DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATASET_PATH.write_text(
        json.dumps([item.as_payload() for item in dataset], indent=2),
        encoding="utf-8",
    )

    case_results: list[EvaluationCaseResult] = []
    summaries: list[dict[str, Any]] = []
    for config in configs:
        metric_inputs: list[MetricInputs] = []
        for item in dataset:
            case_result, metric_input = _evaluate_case(item, config, mode=mode)
            case_results.append(case_result)
            metric_inputs.append(metric_input)
        summary = compute_summary(config=config.name, mode=mode, inputs=metric_inputs)
        summaries.append(summary.as_payload())
        record_ai_evaluation_summary(config=config.name, mode=mode, metrics=summary.as_payload())

    payload = EvaluationRunResult(
        mode=mode,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        dataset_path=str(DATASET_PATH),
        summaries=summaries,
        cases=[asdict(result) for result in case_results],
    )
    if output:
        _write_outputs(payload)
    return payload


def _evaluate_case(
    item: BenchmarkItem,
    config: EvaluationConfig,
    *,
    mode: str,
) -> tuple[EvaluationCaseResult, MetricInputs]:
    started = time.perf_counter()
    settings = get_settings()
    fallback_allowed = mode != "real"
    embedding_provider_name = settings.embedding_provider.lower()
    actual_tools: list[str] = []
    actual_approvals: list[str] = []
    retrieved_documents: list[str] = []
    workflow_valid = False
    error: str | None = None
    planner_started = time.perf_counter()
    try:
        embedding_provider = embedding_provider_from_settings(
            settings,
            allow_fallback=fallback_allowed,
        )
        base_discovery = ToolDiscoveryService(embedding_provider=embedding_provider)
        discovery = AllToolsDiscovery(base_discovery) if config.use_all_tools else base_discovery
        service = WorkflowPlanningService(
            discovery=cast(ToolDiscoveryService, discovery),
            rag=EngineeringRagService(embedding_provider=embedding_provider),
            planner=workflow_planner_from_settings() if mode == "real" else None,
            use_rag=config.use_rag,
            use_capability_graph=config.use_capability_graph,
        )
        result = service.plan(
            WorkflowPlanRequest(
                user_request=item.request,
                role=item.role,
                created_by="evaluation-runner",
                target_environment=item.environment,
                top_k=50 if config.use_all_tools else 12,
            )
        )
        workflow_valid = result.ok
        actual_tools = [node.tool_name for node in result.workflow.nodes]
        actual_approvals = [
            node.tool_name for node in result.workflow.nodes if node.approval_required
        ]
        retrieved_documents = [
            str(entry["citation_id"]) for entry in result.retrieved_knowledge
        ]
    except WorkflowValidationError as exc:
        error = "; ".join(issue.code for issue in exc.issues)
    except Exception as exc:  # noqa: BLE001 - evaluation records failures as data
        error = exc.__class__.__name__
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
        embedding_provider=embedding_provider_name,
        embedding_fallback_allowed=fallback_allowed,
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
                "tool_recall",
                "tool_precision",
                "exact_tool_set_accuracy",
                "workflow_validity_rate",
                "workflow_completion_rate",
                "hallucinated_tool_rate",
                "policy_violation_attempt_rate",
                "approval_classification_accuracy",
                "rag_recall_at_k",
                "rag_mrr",
                "average_workflow_length",
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
