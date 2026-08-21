from __future__ import annotations

import csv
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from mcp_ops_ai_agent.tool_discovery import ToolDiscoveryService
from mcp_ops_ai_agent.tool_discovery.embeddings import HashingEmbeddingProvider
from mcp_ops_ai_agent.tool_discovery.index import InMemoryToolEmbeddingIndex
from mcp_ops_ai_agent.workflows.models import (
    ArgumentReference,
    ConditionOperator,
    PolicyDecision,
    Workflow,
    WorkflowCondition,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeStatus,
    WorkflowPlanDraft,
    WorkflowPlanRequest,
    WorkflowStatus,
)
from mcp_ops_ai_agent.workflows.repository import InMemoryWorkflowRepository
from mcp_ops_ai_agent.workflows.service import WorkflowPlanningService
from mcp_ops_common.config import get_settings
from mcp_ops_mcp_gateway.models import GatewayDecision, GatewayToolRequest, GatewayToolResponse
from mcp_ops_mcp_gateway.service import McpGateway
from mcp_ops_policy.tool_registry import TOOL_REGISTRY
from mcp_ops_repository_mcp.github import OfflineGitHubClient
from mcp_ops_repository_mcp.server import create_dispatcher as create_repository_dispatcher
from mcp_ops_repository_mcp.service import GitHubRepositoryService

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "results"
REPORT_PATH = ROOT / "reports" / "execution-latest.md"
JSON_PATH = RESULTS_DIR / "execution-latest.json"
CSV_PATH = RESULTS_DIR / "execution-latest.csv"


@dataclass(frozen=True, slots=True)
class ExecutionBenchmarkItem:
    id: str
    request: str
    role: str
    environment: str
    expected_tools: list[str]
    required_approvals: list[str]
    expected_terminal_status: str
    expected_succeeded_tools: list[str]
    expected_compensated_tools: list[str]
    expected_retried_tools: list[str]


@dataclass(frozen=True, slots=True)
class ExecutionCaseResult:
    id: str
    request: str
    role: str
    environment: str
    expected_tools: list[str]
    actual_tools: list[str]
    required_approvals: list[str]
    actual_approvals: list[str]
    expected_compensated_tools: list[str]
    expected_retried_tools: list[str]
    planning_success: bool
    policy_correct: bool
    approval_correct: bool
    execution_success: bool
    compensation_success: bool
    retry_recovery: bool
    final_state_correct: bool
    terminal_status: str
    node_statuses: dict[str, str]
    tool_attempts: dict[str, int]
    planner_latency_ms: float
    execution_latency_ms: float
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ExecutionBenchmarkSummary:
    cases: int
    planning_success_rate: float
    policy_correctness_rate: float
    approval_correctness_rate: float
    execution_success_rate: float
    compensation_success_rate: float
    retry_recovery_rate: float
    final_state_correctness_rate: float
    average_planner_latency_ms: float
    average_execution_latency_ms: float

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ExecutionBenchmarkRunResult:
    mode: str
    generated_at: str
    summary: dict[str, Any]
    cases: list[dict[str, Any]]


class ExecutionBenchmarkPlanner:
    """Deterministic planner fixture for execution semantics benchmarking."""

    planner_provider = "deterministic-execution-benchmark"
    planner_model = "execution-benchmark-planner:v1"

    def plan(
        self,
        user_request: str,
        tools: list[Any],
        *,
        role: str,
        target_environment: str = "dev",
        knowledge: list[Any] | None = None,
    ) -> WorkflowPlanDraft:
        del tools, role, target_environment, knowledge
        lowered = user_request.lower()
        if "create issue" in lowered:
            nodes = _build_failure_issue_nodes()
        elif "rerun" in lowered:
            nodes = _build_rerun_workflow_nodes()
        elif "transient" in lowered or "retry" in lowered:
            nodes = [_node("tests", "run_tests", {"repository": _repo(), "branch": "main"})]
        elif "compensate" in lowered:
            nodes = [
                _node(
                    "ticket",
                    "create_ticket",
                    {
                        "device_id": "SIM-014",
                        "title": "Compensating benchmark ticket",
                        "description": "Created by execution benchmark to test compensation.",
                        "priority": "HIGH",
                        "team": "Simulator Operations",
                    },
                )
            ]
        elif "restart" in lowered:
            nodes = [
                _node(
                    "service_restart",
                    "restart_service",
                    {
                        "device_id": "SIM-014",
                        "service_name": "sensor-ingestor",
                        "reason": "Execution benchmark approved service restart.",
                    },
                )
            ]
        else:
            nodes = [_node("status", "get_build_status", {"repository": _repo()})]
        return WorkflowPlanDraft(
            user_request=user_request,
            planner_model=self.planner_model,
            confidence=0.9,
            nodes=nodes,
            edges=_edges_from_nodes(nodes),
        )


class DisabledRagService:
    def search(self, request: object) -> object:
        raise RuntimeError("Execution benchmark disables RAG retrieval.")


class RecordingGatewayClient:
    def __init__(
        self,
        *,
        gateway: McpGateway | None = None,
        transient_failures: dict[str, int] | None = None,
        permanent_failures: set[str] | None = None,
    ) -> None:
        self.gateway = gateway or McpGateway(execution_isolation="inline")
        offline_repository_service = GitHubRepositoryService(
            client=OfflineGitHubClient(_repo()),
        )
        offline_repository_dispatcher = create_repository_dispatcher(
            service=offline_repository_service,
        )
        self.gateway._dispatchers["repository"] = offline_repository_dispatcher
        self.gateway._dispatchers["cicd"] = offline_repository_dispatcher
        self.transient_failures = dict(transient_failures or {})
        self.permanent_failures = set(permanent_failures or set())
        self.requests: list[GatewayToolRequest] = []
        self.responses: list[GatewayToolResponse] = []
        self.approved: list[UUID] = []

    def call_tool(self, request: GatewayToolRequest) -> GatewayToolResponse:
        self.requests.append(request)
        remaining_failures = self.transient_failures.get(request.tool_name, 0)
        if remaining_failures > 0:
            self.transient_failures[request.tool_name] = remaining_failures - 1
            response = _gateway_error(request, "timeout", "Injected deterministic timeout.")
        elif request.tool_name in self.permanent_failures:
            response = _gateway_error(request, "server_500", "Injected deterministic failure.")
        elif request.tool_name == "close_ticket_if_created_by_failed_workflow":
            response = _gateway_ok(
                request,
                {
                    "tool_result": {
                        "ok": True,
                        "data": {
                            "compensated": True,
                            "workflow_id": request.arguments.get("workflow_id"),
                            "failed_node_id": request.arguments.get("failed_node_id"),
                        },
                    }
                },
            )
        else:
            response = self.gateway.call_tool(request)
        self.responses.append(response)
        return response

    def approve(self, approval_id: UUID) -> GatewayToolResponse:
        response = self.gateway.approve_operation("admin-token", approval_id)
        if response.ok:
            self.approved.append(approval_id)
        return response


def run_execution_benchmark(
    *,
    limit: int | None = None,
    output: bool = True,
) -> ExecutionBenchmarkRunResult:
    cases = execution_benchmark_items()
    if limit is not None:
        cases = cases[:limit]
    results = [_run_execution_case(item) for item in cases]
    payload = ExecutionBenchmarkRunResult(
        mode="deterministic-execution",
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        summary=_summarize(results).as_payload(),
        cases=[asdict(result) for result in results],
    )
    if output:
        _write_outputs(payload)
    return payload


def execution_benchmark_items() -> list[ExecutionBenchmarkItem]:
    return [
        ExecutionBenchmarkItem(
            id="EXEC-001",
            request=(
                "Investigate the latest failed build, inspect logs and changes, "
                "then create issue if the failure is code-related."
            ),
            role="ENGINEER",
            environment="dev",
            expected_tools=[
                "get_latest_failed_build",
                "get_failed_jobs",
                "get_pipeline_logs",
                "get_recent_commits",
                "get_changed_files",
                "analyze_build_failure",
                "create_issue",
            ],
            required_approvals=[],
            expected_terminal_status=WorkflowStatus.COMPLETED.value,
            expected_succeeded_tools=[
                "get_latest_failed_build",
                "get_failed_jobs",
                "get_pipeline_logs",
                "get_recent_commits",
                "get_changed_files",
                "analyze_build_failure",
                "create_issue",
            ],
            expected_compensated_tools=[],
            expected_retried_tools=[],
        ),
        ExecutionBenchmarkItem(
            id="EXEC-002",
            request="Run validation tests and rerun the failed workflow after approval.",
            role="OPERATOR",
            environment="staging",
            expected_tools=["get_latest_failed_build", "run_tests", "rerun_workflow"],
            required_approvals=["rerun_workflow"],
            expected_terminal_status=WorkflowStatus.COMPLETED.value,
            expected_succeeded_tools=["get_latest_failed_build", "run_tests", "rerun_workflow"],
            expected_compensated_tools=[],
            expected_retried_tools=[],
        ),
        ExecutionBenchmarkItem(
            id="EXEC-003",
            request="Run tests with one transient timeout and recover through retry.",
            role="ENGINEER",
            environment="dev",
            expected_tools=["run_tests"],
            required_approvals=[],
            expected_terminal_status=WorkflowStatus.COMPLETED.value,
            expected_succeeded_tools=["run_tests"],
            expected_compensated_tools=[],
            expected_retried_tools=["run_tests"],
        ),
        ExecutionBenchmarkItem(
            id="EXEC-004",
            request="Create a ticket, then compensate it if the ticket tool fails.",
            role="ENGINEER",
            environment="dev",
            expected_tools=["create_ticket"],
            required_approvals=[],
            expected_terminal_status=WorkflowStatus.COMPLETED.value,
            expected_succeeded_tools=[],
            expected_compensated_tools=["create_ticket"],
            expected_retried_tools=[],
        ),
        ExecutionBenchmarkItem(
            id="EXEC-005",
            request="Restart the SIM-014 sensor-ingestor service after approval.",
            role="OPERATOR",
            environment="staging",
            expected_tools=["restart_service"],
            required_approvals=["restart_service"],
            expected_terminal_status=WorkflowStatus.COMPLETED.value,
            expected_succeeded_tools=["restart_service"],
            expected_compensated_tools=[],
            expected_retried_tools=[],
        ),
    ]


def _run_execution_case(item: ExecutionBenchmarkItem) -> ExecutionCaseResult:
    repository = InMemoryWorkflowRepository()
    gateway = RecordingGatewayClient(
        transient_failures={"run_tests": 1} if item.id == "EXEC-003" else None,
        permanent_failures={"create_ticket"} if item.id == "EXEC-004" else None,
    )
    embedding_provider = HashingEmbeddingProvider()
    service = WorkflowPlanningService(
        discovery=ToolDiscoveryService(
            embedding_provider=embedding_provider,
            index=InMemoryToolEmbeddingIndex(embedding_provider),
        ),
        planner=ExecutionBenchmarkPlanner(),
        repository=repository,
        gateway_client=gateway,
        rag=cast(Any, DisabledRagService()),
        use_rag=False,
        use_capability_graph=False,
    )
    planner_started = time.perf_counter()
    error: str | None = None
    workflow: Workflow | None = None
    try:
        plan = service.plan(
            WorkflowPlanRequest(
                user_request=item.request,
                created_by="execution-benchmark",
                role=item.role,
                target_environment=item.environment,
                top_k=50,
            )
        )
        workflow = plan.workflow
    except Exception as exc:  # noqa: BLE001 - benchmark failures are recorded as data.
        error = f"{exc.__class__.__name__}: {str(exc)[:240]}"
    planner_latency_ms = (time.perf_counter() - planner_started) * 1000
    execution_started = time.perf_counter()
    if workflow is not None:
        try:
            workflow = _execute_until_terminal(
                service,
                repository,
                gateway,
                workflow,
                role=item.role,
            )
        except Exception as exc:  # noqa: BLE001 - benchmark failures are recorded as data.
            error = f"{exc.__class__.__name__}: {str(exc)[:240]}"
    execution_latency_ms = (time.perf_counter() - execution_started) * 1000
    return _case_result(
        item,
        workflow,
        gateway,
        planning_error=error,
        planner_latency_ms=planner_latency_ms,
        execution_latency_ms=execution_latency_ms,
    )


def _execute_until_terminal(
    service: WorkflowPlanningService,
    repository: InMemoryWorkflowRepository,
    gateway: RecordingGatewayClient,
    workflow: Workflow,
    *,
    role: str,
) -> Workflow:
    current = service.execute(workflow.id, role=role)
    for _ in range(10):
        if current.status == WorkflowStatus.WAITING_APPROVAL:
            for node in current.nodes:
                if (
                    node.execution_status == WorkflowNodeStatus.WAITING_APPROVAL
                    and node.approval_id is not None
                ):
                    gateway.approve(node.approval_id)
            current = service.resume(current.id, role=role)
            continue
        if any(node.execution_status == WorkflowNodeStatus.RETRYING for node in current.nodes):
            current = _make_retries_due(repository, current)
            current = service.resume(current.id, role=role)
            continue
        return current
    return current


def _case_result(
    item: ExecutionBenchmarkItem,
    workflow: Workflow | None,
    gateway: RecordingGatewayClient,
    *,
    planning_error: str | None,
    planner_latency_ms: float,
    execution_latency_ms: float,
) -> ExecutionCaseResult:
    actual_tools = [node.tool_name for node in workflow.nodes] if workflow else []
    actual_approvals = [
        node.tool_name for node in workflow.nodes if node.approval_required
    ] if workflow else []
    node_statuses = {
        node.tool_name: node.execution_status.value for node in workflow.nodes
    } if workflow else {}
    tool_attempts = _tool_attempts(gateway)
    succeeded_tools = {
        node.tool_name
        for node in workflow.nodes
        if node.execution_status == WorkflowNodeStatus.SUCCEEDED
    } if workflow else set()
    compensated_tools = {
        node.tool_name
        for node in workflow.nodes
        if node.execution_status == WorkflowNodeStatus.COMPENSATED
    } if workflow else set()
    retried_tools = {
        tool for tool, attempts in tool_attempts.items() if attempts > 1
    }
    planning_success = workflow is not None and actual_tools == item.expected_tools
    policy_correct = _policy_correct(workflow)
    approval_correct = set(actual_approvals) == set(item.required_approvals)
    execution_success = (
        workflow is not None
        and workflow.status.value == item.expected_terminal_status
        and not planning_error
    )
    compensation_success = set(item.expected_compensated_tools).issubset(compensated_tools)
    retry_recovery = set(item.expected_retried_tools).issubset(retried_tools) and all(
        tool in succeeded_tools for tool in item.expected_retried_tools
    )
    final_state_correct = (
        execution_success
        and set(item.expected_succeeded_tools).issubset(succeeded_tools)
        and set(item.expected_compensated_tools).issubset(compensated_tools)
        and approval_correct
        and retry_recovery
    )
    return ExecutionCaseResult(
        id=item.id,
        request=item.request,
        role=item.role,
        environment=item.environment,
        expected_tools=item.expected_tools,
        actual_tools=actual_tools,
        required_approvals=item.required_approvals,
        actual_approvals=actual_approvals,
        expected_compensated_tools=item.expected_compensated_tools,
        expected_retried_tools=item.expected_retried_tools,
        planning_success=planning_success,
        policy_correct=policy_correct,
        approval_correct=approval_correct,
        execution_success=execution_success,
        compensation_success=compensation_success,
        retry_recovery=retry_recovery,
        final_state_correct=final_state_correct,
        terminal_status=workflow.status.value if workflow else "PLAN_FAILED",
        node_statuses=node_statuses,
        tool_attempts=tool_attempts,
        planner_latency_ms=round(planner_latency_ms, 4),
        execution_latency_ms=round(execution_latency_ms, 4),
        error=planning_error,
    )


def _build_failure_issue_nodes() -> list[WorkflowNode]:
    return [
        _node("latest_build", "get_latest_failed_build", {"repository": _repo()}),
        _node(
            "failed_jobs",
            "get_failed_jobs",
            {"repository": _repo(), "run_id": 0},
            depends_on=["latest_build"],
            refs=[
                ArgumentReference(
                    argument="run_id",
                    source_node_id="latest_build",
                    output_path="data.latest_failed_build.id",
                )
            ],
        ),
        _node(
            "logs",
            "get_pipeline_logs",
            {"repository": _repo(), "job_id": 1, "max_bytes": 12000},
            depends_on=["failed_jobs"],
            refs=[
                ArgumentReference(
                    argument="job_id",
                    source_node_id="failed_jobs",
                    output_path="data.jobs.0.id",
                )
            ],
        ),
        _node(
            "commits",
            "get_recent_commits",
            {"repository": _repo(), "branch": "main", "limit": 5},
        ),
        _node(
            "changed_files",
            "get_changed_files",
            {"repository": _repo(), "head": "abc1234"},
        ),
        _node(
            "analysis",
            "analyze_build_failure",
            {
                "repository": _repo(),
                "logs": "",
                "changed_files": ["src/payments/validation.py"],
                "build_conclusion": "failure",
            },
            depends_on=["latest_build", "logs", "changed_files"],
            refs=[
                ArgumentReference(
                    argument="logs",
                    source_node_id="logs",
                    output_path="data.logs",
                ),
                ArgumentReference(
                    argument="build_conclusion",
                    source_node_id="latest_build",
                    output_path="data.latest_failed_build.conclusion",
                ),
            ],
        ),
        _node(
            "issue",
            "create_issue",
            {
                "repository": _repo(),
                "title": "Investigate code-related build failure",
                "body": "The execution benchmark identified a source-code-related build failure.",
                "labels": ["benchmark", "ci"],
            },
            depends_on=["analysis"],
            condition=WorkflowCondition(
                source_node_id="analysis",
                output_path="data.analysis.source",
                operator=ConditionOperator.EQ,
                value="source_code_failure",
            ),
        ),
    ]


def _build_rerun_workflow_nodes() -> list[WorkflowNode]:
    return [
        _node("latest_build", "get_latest_failed_build", {"repository": _repo()}),
        _node(
            "tests",
            "run_tests",
            {
                "repository": _repo(),
                "branch": "main",
                "test_suite": "smoke",
                "reason": "Execution benchmark validates before rerun.",
            },
            depends_on=["latest_build"],
        ),
        _node(
            "rerun",
            "rerun_workflow",
            {"repository": _repo(), "run_id": 0, "reason": "Approved execution benchmark rerun."},
            depends_on=["latest_build", "tests"],
            refs=[
                ArgumentReference(
                    argument="run_id",
                    source_node_id="latest_build",
                    output_path="data.latest_failed_build.id",
                )
            ],
        ),
    ]


def _node(
    node_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    depends_on: list[str] | None = None,
    refs: list[ArgumentReference] | None = None,
    condition: WorkflowCondition | None = None,
) -> WorkflowNode:
    metadata = TOOL_REGISTRY[tool_name]
    return WorkflowNode(
        id=node_id,
        tool_name=tool_name,
        tool_server=metadata.server,
        description=metadata.description,
        arguments=arguments,
        argument_references=refs or [],
        depends_on=depends_on or [],
        typed_condition=condition,
        risk_level=metadata.risk_level.value,
        approval_required=metadata.requires_approval,
    )


def _edges_from_nodes(nodes: list[WorkflowNode]) -> list[WorkflowEdge]:
    return [
        WorkflowEdge(source=dependency, destination=node.id)
        for node in nodes
        for dependency in node.depends_on
    ]


def _policy_correct(workflow: Workflow | None) -> bool:
    if workflow is None:
        return False
    for node in workflow.nodes:
        evaluation = node.policy_evaluation
        if evaluation is None:
            return False
        if node.approval_required and evaluation.decision != PolicyDecision.ALLOW_WITH_APPROVAL:
            return False
        if not node.approval_required and evaluation.decision == PolicyDecision.DENY:
            return False
    return True


def _make_retries_due(
    repository: InMemoryWorkflowRepository,
    workflow: Workflow,
) -> Workflow:
    due = datetime.now(UTC) - timedelta(seconds=1)
    nodes = [
        node.model_copy(update={"next_retry_at": due})
        if node.execution_status == WorkflowNodeStatus.RETRYING
        else node
        for node in workflow.nodes
    ]
    return repository.save_workflow(workflow.model_copy(update={"nodes": nodes}, deep=True))


def _tool_attempts(gateway: RecordingGatewayClient) -> dict[str, int]:
    attempts: dict[str, int] = {}
    for request in gateway.requests:
        attempts[request.tool_name] = attempts.get(request.tool_name, 0) + 1
    return attempts


def _summarize(results: list[ExecutionCaseResult]) -> ExecutionBenchmarkSummary:
    denominator = max(1, len(results))
    return ExecutionBenchmarkSummary(
        cases=len(results),
        planning_success_rate=_rate(results, "planning_success", denominator),
        policy_correctness_rate=_rate(results, "policy_correct", denominator),
        approval_correctness_rate=_rate(results, "approval_correct", denominator),
        execution_success_rate=_rate(results, "execution_success", denominator),
        compensation_success_rate=_applicable_rate(
            results,
            "compensation_success",
            lambda result: bool(result.expected_compensated_tools),
        ),
        retry_recovery_rate=_applicable_rate(
            results,
            "retry_recovery",
            lambda result: bool(result.expected_retried_tools),
        ),
        final_state_correctness_rate=_rate(results, "final_state_correct", denominator),
        average_planner_latency_ms=round(
            sum(result.planner_latency_ms for result in results) / denominator,
            4,
        ),
        average_execution_latency_ms=round(
            sum(result.execution_latency_ms for result in results) / denominator,
            4,
        ),
    )


def _rate(results: list[ExecutionCaseResult], field_name: str, denominator: int) -> float:
    return round(
        sum(1 for result in results if bool(getattr(result, field_name))) / denominator,
        4,
    )


def _applicable_rate(
    results: list[ExecutionCaseResult],
    field_name: str,
    applies: Any,
) -> float:
    applicable = [result for result in results if bool(applies(result))]
    denominator = max(1, len(applicable))
    return round(
        sum(1 for result in applicable if bool(getattr(result, field_name))) / denominator,
        4,
    )


def _write_outputs(payload: ExecutionBenchmarkRunResult) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload_dict = asdict(payload)
    JSON_PATH.write_text(json.dumps(payload_dict, indent=2), encoding="utf-8")
    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = list(payload.summary)
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(payload.summary)
    REPORT_PATH.write_text(_render_execution_report(payload), encoding="utf-8")


def _render_execution_report(payload: ExecutionBenchmarkRunResult) -> str:
    summary = payload.summary
    lines = [
        "# AI Engineering Workflow Execution Benchmark",
        "",
        f"Generated: `{payload.generated_at}`",
        f"Mode: `{payload.mode}`",
        "",
        "This benchmark uses deterministic MCP/tool simulators. It measures execution engine "
        "semantics, not live LLM quality.",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key, value in summary.items():
        lines.append(f"| {key} | {value} |")
    lines.extend(
        [
            "",
            "## Cases",
            "",
            "| Case | Terminal | Planning | Policy | Approval | Execution | Retry | "
            "Compensation | Final State |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for case in payload.cases:
        lines.append(
            f"| {case['id']} | {case['terminal_status']} | "
            f"{_bool(case['planning_success'])} | {_bool(case['policy_correct'])} | "
            f"{_bool(case['approval_correct'])} | {_bool(case['execution_success'])} | "
            f"{_applicable_bool(case, 'retry_recovery', 'expected_retried_tools')} | "
            f"{_applicable_bool(case, 'compensation_success', 'expected_compensated_tools')} | "
            f"{_bool(case['final_state_correct'])} |"
        )
    return "\n".join(lines) + "\n"


def _gateway_ok(request: GatewayToolRequest, data: dict[str, Any]) -> GatewayToolResponse:
    return GatewayToolResponse(
        ok=True,
        decision=GatewayDecision.ALLOWED,
        correlation_id=uuid4(),
        data=data,
    )


def _gateway_error(
    request: GatewayToolRequest,
    code: str,
    message: str,
) -> GatewayToolResponse:
    return GatewayToolResponse(
        ok=False,
        decision=GatewayDecision.DENIED,
        correlation_id=request.correlation_id,
        data={"tool_name": request.tool_name},
        error={"code": code, "message": message},
    )


def _repo() -> str:
    settings = get_settings()
    if settings.github_owner and settings.github_repo:
        return f"{settings.github_owner}/{settings.github_repo}"
    return "ImmanuelP31/MCP_AI"


def _bool(value: object) -> str:
    return "yes" if bool(value) else "no"


def _applicable_bool(case: dict[str, Any], result_key: str, expected_key: str) -> str:
    expected = case.get(expected_key)
    if not isinstance(expected, list) or not expected:
        return "n/a"
    return _bool(case.get(result_key))
