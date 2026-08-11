from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from mcp_ops_ai_agent.gateway import GatewayClient
from mcp_ops_ai_agent.workflows.events import InMemoryWorkflowEventPublisher
from mcp_ops_ai_agent.workflows.models import (
    RetryStrategy,
    Workflow,
    WorkflowNode,
    WorkflowNodeStatus,
    WorkflowStatus,
)
from mcp_ops_ai_agent.workflows.repository import InMemoryWorkflowRepository
from mcp_ops_ai_agent.workflows.service import WorkflowPlanningService
from mcp_ops_mcp_gateway.models import GatewayDecision, GatewayToolRequest, GatewayToolResponse
from mcp_ops_observability.metrics import metrics_response


def test_mcp_timeout_retries_failed_node_without_restarting_successful_nodes() -> None:
    repository = InMemoryWorkflowRepository()
    workflow = repository.save_workflow(
        _workflow([_node("get_commit"), _node("ticket", depends_on=["get_commit"])])
    )
    gateway = SequencedGateway([_ok(), TimeoutError("MCP timeout"), _ok()])
    service = WorkflowPlanningService(repository=repository, gateway_client=gateway)

    executed = service.execute(workflow.id, role="ENGINEER")

    nodes = {node.id: node for node in executed.nodes}
    assert executed.status == WorkflowStatus.COMPLETED
    assert nodes["get_commit"].attempts == 1
    assert nodes["ticket"].attempts == 2
    assert nodes["ticket"].execution_status == WorkflowNodeStatus.SUCCEEDED


def test_network_failure_tool_500_and_server_unavailable_can_retry() -> None:
    failures: list[GatewayToolResponse | BaseException] = [
        ConnectionError("network failure"),
        _failed("server_500", "tool returned 500"),
        RuntimeError("tool server unavailable"),
    ]
    for failure in failures:
        repository = InMemoryWorkflowRepository()
        workflow = repository.save_workflow(_workflow([_node("ticket")]))
        gateway = SequencedGateway([failure, _ok()])
        service = WorkflowPlanningService(repository=repository, gateway_client=gateway)

        executed = service.execute(workflow.id, role="ENGINEER")

        node = executed.nodes[0]
        assert executed.status == WorkflowStatus.COMPLETED
        assert node.execution_status == WorkflowNodeStatus.SUCCEEDED
        assert node.attempts == 2


def test_malformed_tool_output_fails_safely() -> None:
    repository = InMemoryWorkflowRepository()
    workflow = repository.save_workflow(_workflow([_node("ticket", max_retries=0)]))
    service = WorkflowPlanningService(
        repository=repository,
        gateway_client=MalformedGateway(),
    )

    executed = service.execute(workflow.id, role="ENGINEER")

    node = executed.nodes[0]
    assert executed.status == WorkflowStatus.FAILED
    assert node.execution_status == WorkflowNodeStatus.FAILED
    assert node.last_error == "malformed tool output"


def test_compensation_runs_only_when_tool_declares_compensation() -> None:
    repository = InMemoryWorkflowRepository()
    workflow = repository.save_workflow(
        _workflow(
            [
                _node(
                    "ticket",
                    max_retries=0,
                    compensation_tool="close_ticket_if_created_by_failed_workflow",
                )
            ]
        )
    )
    gateway = SequencedGateway([_failed("server_500", "ticket creation failed"), _ok()])
    service = WorkflowPlanningService(repository=repository, gateway_client=gateway)

    executed = service.execute(workflow.id, role="ENGINEER")

    node = executed.nodes[0]
    assert executed.status == WorkflowStatus.COMPLETED
    assert node.execution_status == WorkflowNodeStatus.COMPENSATED
    assert gateway.requests[-1].tool_name == "close_ticket_if_created_by_failed_workflow"


def test_policy_change_midway_does_not_rerun_completed_nodes() -> None:
    repository = InMemoryWorkflowRepository()
    workflow = _workflow(
        [
            _node("completed"),
            _node("ticket", depends_on=["completed"]),
        ]
    )
    completed = workflow.nodes[0].model_copy(
        update={"execution_status": WorkflowNodeStatus.SUCCEEDED, "attempts": 1}
    )
    workflow = workflow.model_copy(update={"nodes": [completed, workflow.nodes[1]]})
    repository.save_workflow(workflow)
    service = WorkflowPlanningService(
        repository=repository,
        gateway_client=SequencedGateway([_ok()]),
    )

    executed = service.resume(workflow.id, role="VIEWER")

    nodes = {node.id: node for node in executed.nodes}
    assert nodes["completed"].attempts == 1
    assert nodes["ticket"].execution_status == WorkflowNodeStatus.DENIED
    assert executed.status == WorkflowStatus.FAILED


def test_expired_approval_fails_on_resume_without_execution() -> None:
    repository = InMemoryWorkflowRepository()
    old = datetime.now(UTC) - timedelta(minutes=10)
    waiting = _node("restart", tool_name="restart_service", max_retries=0).model_copy(
        update={
            "execution_status": WorkflowNodeStatus.WAITING_APPROVAL,
            "last_attempt_at": old,
            "timeout_seconds": 1,
            "result_reference": str(uuid4()),
        }
    )
    workflow = repository.save_workflow(
        _workflow([waiting]).model_copy(update={"status": WorkflowStatus.WAITING_APPROVAL})
    )
    gateway = SequencedGateway([_ok()])
    service = WorkflowPlanningService(repository=repository, gateway_client=gateway)

    executed = service.resume(workflow.id, role="OPERATOR")

    node = executed.nodes[0]
    assert executed.status == WorkflowStatus.FAILED
    assert node.last_error == "approval expired before workflow resume"
    assert gateway.requests == []


def test_kafka_publish_unavailable_does_not_lose_checkpoint() -> None:
    repository = InMemoryWorkflowRepository()
    workflow = repository.save_workflow(_workflow([_node("ticket")]))
    publisher = InMemoryWorkflowEventPublisher(fail_publish=True)
    service = WorkflowPlanningService(
        repository=repository,
        gateway_client=SequencedGateway([_ok()]),
        event_publisher=publisher,
    )

    executed = service.execute(workflow.id, role="ENGINEER")

    assert executed.status == WorkflowStatus.COMPLETED
    assert any(
        event.event_type == "workflow.event_publish_failed" for event in executed.audit_events
    )


def test_redis_unavailable_retry_and_backend_restart_recovery() -> None:
    repository = InMemoryWorkflowRepository()
    workflow = repository.save_workflow(_workflow([_node("ticket", max_retries=0)]))
    first_service = WorkflowPlanningService(
        repository=repository,
        gateway_client=SequencedGateway([RuntimeError("Redis unavailable")]),
    )

    failed = first_service.execute(workflow.id, role="ENGINEER")
    assert failed.nodes[0].execution_status == WorkflowNodeStatus.FAILED

    second_service = WorkflowPlanningService(
        repository=repository,
        gateway_client=SequencedGateway([_ok()]),
    )
    recovered = second_service.retry_node(workflow.id, "ticket", role="ENGINEER")

    assert recovered.status == WorkflowStatus.COMPLETED
    assert recovered.nodes[0].attempts == 2


def test_resiliency_metrics_are_emitted() -> None:
    repository = InMemoryWorkflowRepository()
    workflow = repository.save_workflow(_workflow([_node("ticket")]))
    service = WorkflowPlanningService(
        repository=repository,
        gateway_client=SequencedGateway([TimeoutError("timeout"), _ok()]),
    )

    service.execute(workflow.id, role="ENGINEER")

    metrics = metrics_response().decode("utf-8")
    assert "workflow_executions_total" in metrics
    assert "workflow_retries_total" in metrics
    assert "workflow_execution_duration_seconds" in metrics


class SequencedGateway(GatewayClient):
    def __init__(self, responses: list[GatewayToolResponse | BaseException]) -> None:
        self.responses = responses
        self.requests: list[GatewayToolRequest] = []

    def call_tool(self, request: GatewayToolRequest) -> GatewayToolResponse:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class MalformedGateway(GatewayClient):
    def call_tool(self, request: GatewayToolRequest) -> Any:
        return type(
            "MalformedResponse",
            (),
            {
                "ok": True,
                "decision": GatewayDecision.ALLOWED,
                "correlation_id": uuid4(),
                "data": ["not", "a", "dict"],
                "error": None,
            },
        )()


def _workflow(nodes: list[WorkflowNode]) -> Workflow:
    workflow = Workflow(
        user_request="Run resilient workflow.",
        status=WorkflowStatus.VALIDATED,
        created_by="engineer",
        planner_model="test",
        confidence=0.9,
        nodes=nodes,
    )
    return workflow.model_copy(
        update={"nodes": [node.model_copy(update={"workflow_id": workflow.id}) for node in nodes]}
    )


def _node(
    node_id: str,
    *,
    tool_name: str = "create_ticket",
    depends_on: list[str] | None = None,
    max_retries: int = 1,
    compensation_tool: str | None = None,
) -> WorkflowNode:
    return WorkflowNode(
        id=node_id,
        tool_name=tool_name,
        tool_server="ticket-mcp",
        description=f"Run {tool_name}.",
        arguments={
            "device_id": "SIM-014",
            "title": "Workflow ticket",
            "description": "Resilient workflow test",
            "priority": "HIGH",
            "team": "Engineering Operations",
            "diagnostic_evidence": {"source": "test"},
        },
        depends_on=depends_on or [],
        risk_level="MEDIUM",
        max_retries=max_retries,
        retry_strategy=RetryStrategy.FIXED_DELAY if max_retries else RetryStrategy.NO_RETRY,
        compensation_tool=compensation_tool,
    )


def _ok() -> GatewayToolResponse:
    return GatewayToolResponse(
        ok=True,
        decision=GatewayDecision.ALLOWED,
        correlation_id=uuid4(),
        data={"tool_result": {"ok": True}},
    )


def _failed(code: str, message: str) -> GatewayToolResponse:
    return GatewayToolResponse(
        ok=False,
        decision=GatewayDecision.DENIED,
        correlation_id=uuid4(),
        data={},
        error={"code": code, "message": message},
    )
