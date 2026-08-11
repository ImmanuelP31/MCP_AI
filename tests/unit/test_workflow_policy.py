from __future__ import annotations

import json

import pytest
from mcp_ops_ai_agent.workflows.models import WorkflowNode, WorkflowPlanRequest
from mcp_ops_ai_agent.workflows.planner import JsonWorkflowPlanner, PlannerOutputError
from mcp_ops_ai_agent.workflows.policy import WorkflowPolicyEvaluator
from mcp_ops_ai_agent.workflows.service import WorkflowPlanningService
from mcp_ops_observability.metrics import metrics_response


def test_role_policy_differs_for_developer_operator_and_admin() -> None:
    evaluator = WorkflowPolicyEvaluator()
    node = _node("restart", "restart_service")

    developer = evaluator.evaluate(
        node, actor="developer", role="ENGINEER", environment="production", phase="planning"
    )
    operator = evaluator.evaluate(
        node, actor="operator", role="OPERATOR", environment="production", phase="planning"
    )
    admin = evaluator.evaluate(
        node, actor="admin", role="ADMIN", environment="production", phase="planning"
    )

    assert developer.decision == "DENY"
    assert operator.decision == "ALLOW_WITH_APPROVAL"
    assert admin.decision == "ALLOW_WITH_APPROVAL"


def test_environment_policy_differs_for_dev_staging_and_production() -> None:
    evaluator = WorkflowPolicyEvaluator()
    node = _node("restart", "restart_service")

    dev = evaluator.evaluate(
        node, actor="operator", role="OPERATOR", environment="dev", phase="planning"
    )
    staging = evaluator.evaluate(
        node, actor="operator", role="OPERATOR", environment="staging", phase="planning"
    )
    production = evaluator.evaluate(
        node, actor="operator", role="OPERATOR", environment="production", phase="planning"
    )

    assert dev.decision == "ALLOW"
    assert staging.decision == "ALLOW_WITH_APPROVAL"
    assert production.decision == "ALLOW_WITH_APPROVAL"


def test_critical_production_action_is_denied_for_operator() -> None:
    evaluation = WorkflowPolicyEvaluator().evaluate(
        _node("delete", "delete_bad_deployment", arguments={"deployment_id": "deploy-2026-08-11"}),
        actor="operator",
        role="OPERATOR",
        environment="production",
        phase="planning",
    )

    assert evaluation.decision == "DENY"
    assert evaluation.policy_rule == "environment.production.critical"


def test_high_risk_production_workflow_gets_approval_gate() -> None:
    result = WorkflowPlanningService().plan(
        WorkflowPlanRequest(
            user_request="Restart SIM-014 service.",
            role="OPERATOR",
            created_by="operator",
            target_environment="production",
            top_k=10,
        )
    )

    restart = next(node for node in result.workflow.nodes if node.tool_name == "restart_service")
    assert restart.approval_required is True
    assert restart.policy_evaluation is not None
    assert restart.policy_evaluation.decision == "ALLOW_WITH_APPROVAL"


def test_policy_is_rechecked_immediately_before_execution() -> None:
    service = WorkflowPlanningService()
    planned = service.plan(
        WorkflowPlanRequest(
            user_request="Restart SIM-014 service.",
            role="OPERATOR",
            created_by="operator",
            target_environment="production",
            top_k=10,
        )
    ).workflow
    restart_before = next(node for node in planned.nodes if node.tool_name == "restart_service")
    assert restart_before.policy_evaluation is not None

    executed = service.execute(planned.id, role="OPERATOR")
    restart_after = next(node for node in executed.nodes if node.tool_name == "restart_service")

    assert restart_after.policy_evaluation is not None
    assert restart_after.policy_evaluation.timestamp >= restart_before.policy_evaluation.timestamp
    assert restart_after.execution_status == "WAITING_APPROVAL"


def test_approval_replay_does_not_create_duplicate_execution() -> None:
    service = WorkflowPlanningService()
    planned = service.plan(
        WorkflowPlanRequest(
            user_request="Restart SIM-014 service.",
            role="OPERATOR",
            created_by="operator",
            target_environment="production",
            top_k=10,
        )
    ).workflow

    first = service.execute(planned.id, role="OPERATOR")
    second = service.execute(planned.id, role="OPERATOR")

    first_restart = next(node for node in first.nodes if node.tool_name == "restart_service")
    second_restart = next(node for node in second.nodes if node.tool_name == "restart_service")
    assert first.status == "WAITING_APPROVAL"
    assert second.status == "WAITING_APPROVAL"
    assert second_restart.result_reference == first_restart.result_reference


def test_llm_cannot_downgrade_risk_or_approval_requirement() -> None:
    payload = {
        "user_request": "Restart SIM-014 service.",
        "planner_model": "test",
        "confidence": 0.8,
        "nodes": [
            _node(
                "restart",
                "restart_service",
                risk_level="READ_ONLY",
                approval_required=False,
            ).model_dump(mode="json")
        ],
        "edges": [],
    }
    service = WorkflowPlanningService(planner=JsonWorkflowPlanner(json.dumps(payload)))

    result = service.plan(
        WorkflowPlanRequest(
            user_request="Restart SIM-014 service.",
            role="OPERATOR",
            created_by="operator",
            target_environment="production",
            top_k=10,
        )
    )

    restart = result.workflow.nodes[0]
    assert restart.risk_level == "HIGH"
    assert restart.approval_required is True
    assert restart.policy_evaluation is not None
    assert restart.policy_evaluation.decision == "ALLOW_WITH_APPROVAL"
    assert "policy_bypass_attempts_total" in metrics_response().decode("utf-8")


def test_llm_authorized_field_is_rejected_by_schema() -> None:
    payload = {
        "user_request": "Restart SIM-014 service.",
        "planner_model": "test",
        "confidence": 0.8,
        "nodes": [
            {
                **_node("restart", "restart_service").model_dump(mode="json"),
                "authorized": True,
            }
        ],
        "edges": [],
    }

    with pytest.raises(PlannerOutputError):
        JsonWorkflowPlanner(json.dumps(payload)).plan(
            "Restart SIM-014 service.",
            [],
            role="OPERATOR",
        )


def test_policy_metrics_are_emitted() -> None:
    evaluator = WorkflowPolicyEvaluator()
    evaluator.evaluate(
        _node("delete", "delete_bad_deployment", arguments={"deployment_id": "deploy-1"}),
        actor="operator",
        role="OPERATOR",
        environment="production",
        phase="planning",
    )
    evaluator.evaluate(
        _node("restart", "restart_service"),
        actor="operator",
        role="OPERATOR",
        environment="production",
        phase="planning",
    )

    metrics = metrics_response().decode("utf-8")
    assert "policy_evaluations_total" in metrics
    assert "policy_denials_total" in metrics
    assert "policy_approval_required_total" in metrics


def _node(
    node_id: str,
    tool_name: str,
    *,
    arguments: dict[str, object] | None = None,
    risk_level: str = "LOW",
    approval_required: bool = False,
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
        risk_level=risk_level,
        approval_required=approval_required,
    )
