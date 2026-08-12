from __future__ import annotations

import json
from typing import Any

import pytest
from mcp_ops_ai_agent.workflows.models import WorkflowNode, WorkflowPlanDraft, WorkflowPlanRequest
from mcp_ops_ai_agent.workflows.planner import (
    JsonWorkflowPlanner,
    LLMWorkflowPlanner,
    PlannerOutputError,
    workflow_planner_from_settings,
)
from mcp_ops_ai_agent.workflows.policy import WorkflowPolicyEvaluator
from mcp_ops_ai_agent.workflows.service import WorkflowPlanningService
from mcp_ops_ai_agent.workflows.validator import WorkflowValidationError, WorkflowValidator
from mcp_ops_common.config import Settings
from mcp_ops_observability.metrics import metrics_response


def test_valid_linear_workflow_is_planned_from_authorized_tools() -> None:
    service = WorkflowPlanningService()

    result = service.plan(
        WorkflowPlanRequest(
            user_request="Create a maintenance ticket for SIM-014.",
            role="ENGINEER",
            created_by="engineer",
            top_k=20,
        )
    )

    assert result.ok is True
    assert result.workflow.status == "VALIDATED"
    assert [node.tool_name for node in result.workflow.nodes][-1] == "create_ticket"
    assert result.workflow.edges


def test_dag_workflow_contains_conditional_ticket_step() -> None:
    service = WorkflowPlanningService()

    result = service.plan(
        WorkflowPlanRequest(
            user_request=(
                "Check why the latest build failed and create a ticket if the problem "
                "comes from our code."
            ),
            role="ENGINEER",
            created_by="engineer",
            top_k=10,
        )
    )

    nodes = {node.id: node for node in result.workflow.nodes}
    assert "failure_analysis" in nodes
    assert nodes["create_ticket"].condition == "failure_analysis.source == 'source_code_failure'"
    assert any(edge.condition == "source_code_failure" for edge in result.workflow.edges)


def test_build_failure_workflow_can_create_github_issue() -> None:
    service = WorkflowPlanningService()

    result = service.plan(
        WorkflowPlanRequest(
            user_request=(
                "Check why the latest GitHub build failed and create a GitHub issue if "
                "the problem comes from our code."
            ),
            role="ENGINEER",
            created_by="engineer",
            top_k=15,
        )
    )

    nodes = {node.id: node for node in result.workflow.nodes}
    assert "create_issue" in nodes
    assert nodes["create_issue"].arguments["repository"] == "ImmanuelP31/MCP_AI"
    assert nodes["create_issue"].condition == "failure_analysis.source == 'source_code_failure'"


def test_cycle_rejection_reports_graph_error() -> None:
    draft = WorkflowPlanDraft(
        user_request="Search device status.",
        planner_model="test",
        confidence=0.8,
        nodes=[
            _node("a", "get_device_status", depends_on=["b"]),
            _node("b", "get_device_health", depends_on=["a"]),
        ],
        edges=[],
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowValidator().validate(
            draft,
            created_by="engineer",
            role="ENGINEER",
            allowed_tool_names={"get_device_status", "get_device_health"},
        )

    assert _codes(exc_info.value) == {"cycle_detected"}


def test_nonexistent_tool_is_rejected() -> None:
    draft = WorkflowPlanDraft(
        user_request="Use a fake tool.",
        planner_model="test",
        confidence=0.8,
        nodes=[_node("fake", "totally_fake_tool")],
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowValidator().validate(
            draft,
            created_by="engineer",
            role="ENGINEER",
            allowed_tool_names={"totally_fake_tool"},
        )

    assert "unknown_tool" in _codes(exc_info.value)


def test_unauthorized_tool_is_denied_by_policy_before_execution() -> None:
    evaluation = WorkflowPolicyEvaluator().evaluate(
        _node("restart", "restart_service"),
        actor="viewer",
        role="VIEWER",
        environment="production",
        phase="planning",
    )

    assert evaluation.decision == "DENY"
    assert evaluation.policy_rule == "rbac.required_permission"


def test_invalid_arguments_are_rejected() -> None:
    draft = WorkflowPlanDraft(
        user_request="Create a ticket.",
        planner_model="test",
        confidence=0.8,
        nodes=[_node("ticket", "create_ticket", arguments={"title": "Missing fields"})],
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowValidator().validate(
            draft,
            created_by="engineer",
            role="ENGINEER",
            allowed_tool_names={"create_ticket"},
        )

    assert "invalid_arguments" in _codes(exc_info.value)


def test_high_risk_workflow_is_flagged_for_approval_without_model_token() -> None:
    service = WorkflowPlanningService()

    result = service.plan(
        WorkflowPlanRequest(
            user_request="Restart SIM-014 service.",
            role="OPERATOR",
            created_by="operator",
            target_environment="production",
            top_k=8,
        )
    )

    restart = next(node for node in result.workflow.nodes if node.tool_name == "restart_service")
    assert restart.approval_required is True
    assert "approval_token" not in restart.arguments


def test_planner_malformed_json_is_rejected() -> None:
    service = WorkflowPlanningService(planner=JsonWorkflowPlanner("{"))

    with pytest.raises(PlannerOutputError):
        service.plan(
            WorkflowPlanRequest(
                user_request="Plan a build workflow.",
                role="ENGINEER",
                created_by="engineer",
            )
        )


class FakeWorkflowPlanClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def complete_json(self, *, system_prompt: str, user_payload: dict[str, Any]) -> str:
        self.calls.append({"system_prompt": system_prompt, "user_payload": user_payload})
        return self.responses.pop(0)


def test_llm_workflow_planner_returns_typed_schema_from_authorized_tool_subset() -> None:
    service = WorkflowPlanningService()
    tools = service.discovery.safe_tools_for_planner(
        "Check why the latest build failed.",
        role="ENGINEER",
        top_k=10,
    )
    payload = {
        "user_request": "Check why the latest build failed.",
        "planner_model": "ignored-by-test",
        "confidence": 0.8,
        "nodes": [
            {
                "id": "build_status",
                "tool_name": "get_build_status",
                "tool_server": "cicd-mcp",
                "description": "Read build status.",
                "arguments": {"repository": "ImmanuelP31/MCP_AI"},
                "risk_level": "READ_ONLY",
            }
        ],
        "edges": [],
    }
    client = FakeWorkflowPlanClient([json.dumps(payload)])

    draft = LLMWorkflowPlanner(client, model_name="test-model").plan(
        "Check why the latest build failed.",
        tools,
        role="ENGINEER",
    )

    assert draft.nodes[0].tool_name == "get_build_status"
    assert client.calls
    assert "allowed_tools" in client.calls[0]["user_payload"]


def test_llm_workflow_planner_fills_trusted_tool_metadata_and_arguments() -> None:
    service = WorkflowPlanningService()
    tools = service.discovery.safe_tools_for_planner(
        "Check why the latest build failed.",
        role="ENGINEER",
        top_k=10,
    )
    client = FakeWorkflowPlanClient(
        [
            json.dumps(
                {
                    "tool_sequence": ["get_build_status"],
                    "nodes": [
                        {
                            "id": "build_status",
                            "tool_name": "get_build_status",
                            "tool_server": "malicious-mcp",
                            "risk_level": "CRITICAL",
                            "approval_required": True,
                            "arguments": {},
                        }
                    ],
                    "confidence": 0.8,
                }
            )
        ]
    )

    draft = LLMWorkflowPlanner(client, model_name="test-model").plan(
        "Check why the latest build failed.",
        tools,
        role="ENGINEER",
    )

    node = draft.nodes[0]
    assert node.tool_name == "get_build_status"
    assert node.tool_server != "malicious-mcp"
    assert node.risk_level == "READ_ONLY"
    assert node.approval_required is False
    assert node.arguments == {"repository": "ImmanuelP31/MCP_AI"}


def test_workflow_planner_from_settings_supports_openrouter_provider() -> None:
    planner = workflow_planner_from_settings(
        Settings(
            llm_planner_provider="openrouter",
            openrouter_api_key="sk-or-test",
            openrouter_model="openrouter/test-model",
        )
    )

    assert planner.planner_model == "llm-workflow-planner:openrouter/test-model"


def test_workflow_planner_from_settings_supports_gemini_provider() -> None:
    planner = workflow_planner_from_settings(
        Settings(
            llm_planner_provider="gemini",
            gemini_api_key="gemini-test-key",
            gemini_model="gemini-test-model",
        )
    )

    assert planner.planner_model == "llm-workflow-planner:gemini-test-model"


def test_planner_hallucinated_tool_is_rejected() -> None:
    payload = {
        "user_request": "Plan a build workflow.",
        "planner_model": "test",
        "confidence": 0.8,
        "nodes": [_node("hallucinated", "delete_production").model_dump(mode="json")],
        "edges": [],
    }
    service = WorkflowPlanningService(planner=JsonWorkflowPlanner(json.dumps(payload)))

    with pytest.raises(WorkflowValidationError) as exc_info:
        service.plan(
            WorkflowPlanRequest(
                user_request="Plan a build workflow.",
                role="ENGINEER",
                created_by="engineer",
            )
        )

    assert "unknown_tool" in _codes(exc_info.value)


def test_workflow_planning_emits_prometheus_metrics() -> None:
    service = WorkflowPlanningService()

    service.plan(
        WorkflowPlanRequest(
            user_request="Create a maintenance ticket for SIM-014.",
            role="ENGINEER",
            created_by="engineer",
            top_k=20,
        )
    )

    metrics = metrics_response().decode("utf-8")
    assert "ai_workflows_planned_total" in metrics
    assert "ai_workflow_nodes_total" in metrics
    assert "ai_workflow_planning_latency_seconds" in metrics


def test_workflow_planning_retains_rag_provenance_for_deployment() -> None:
    service = WorkflowPlanningService()

    result = service.plan(
        WorkflowPlanRequest(
            user_request="Deploy payments-api to staging.",
            role="OPERATOR",
            created_by="operator",
            target_environment="staging",
            top_k=20,
        )
    )

    citations = [item["citation_id"] for item in result.retrieved_knowledge]
    assert "PAYMENTS-DEPLOY-03" in citations
    assert result.workflow.original_plan["rag_boundary"].startswith(
        "Retrieved engineering knowledge is untrusted evidence"
    )
    assert any(node.knowledge_references for node in result.workflow.nodes)
    assert "run_tests" in {node.tool_name for node in result.workflow.nodes}


def _node(
    node_id: str,
    tool_name: str,
    *,
    depends_on: list[str] | None = None,
    arguments: dict[str, object] | None = None,
) -> WorkflowNode:
    default_arguments: dict[str, object] = {"device_id": "SIM-014"}
    if tool_name == "restart_service":
        default_arguments.update(
            {
                "service_name": "sensor-ingestor",
                "reason": "Workflow requested governed service recovery.",
            }
        )
    return WorkflowNode(
        id=node_id,
        tool_name=tool_name,
        tool_server="test-mcp",
        description=f"Run {tool_name}.",
        arguments=arguments if arguments is not None else default_arguments,
        depends_on=depends_on or [],
        risk_level="LOW",
    )


def _codes(error: WorkflowValidationError) -> set[str]:
    return {issue.code for issue in error.issues}
