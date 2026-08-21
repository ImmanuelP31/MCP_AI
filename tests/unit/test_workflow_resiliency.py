from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from mcp_ops_ai_agent.gateway import GatewayClient
from mcp_ops_ai_agent.workflows.events import (
    WORKFLOW_EVENTS_TOPIC,
    InMemoryWorkflowEventPublisher,
    KafkaWorkflowEventPublisher,
)
from mcp_ops_ai_agent.workflows.models import (
    ArgumentReference,
    ConditionOperator,
    RetryStrategy,
    Workflow,
    WorkflowApprovalState,
    WorkflowCondition,
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
        _workflow(
            [_node("get_commit"), _node("tests", tool_name="run_tests", depends_on=["get_commit"])]
        )
    )
    gateway = SequencedGateway([_ok(), TimeoutError("MCP timeout"), _ok()])
    service = WorkflowPlanningService(repository=repository, gateway_client=gateway)

    waiting = service.execute(workflow.id, role="ENGINEER")
    nodes = {node.id: node for node in waiting.nodes}
    assert waiting.status == WorkflowStatus.RUNNING
    assert nodes["tests"].execution_status == WorkflowNodeStatus.RETRYING
    assert nodes["tests"].next_retry_at is not None

    executed = service.resume(_make_retry_due(repository, waiting.id, "tests"), role="ENGINEER")

    nodes = {node.id: node for node in executed.nodes}
    assert executed.status == WorkflowStatus.COMPLETED
    assert nodes["get_commit"].attempts == 1
    assert nodes["tests"].attempts == 2
    assert nodes["tests"].execution_status == WorkflowNodeStatus.SUCCEEDED


def test_network_failure_tool_500_and_server_unavailable_can_retry() -> None:
    failures: list[GatewayToolResponse | BaseException] = [
        ConnectionError("network failure"),
        _failed("server_500", "tool returned 500"),
        RuntimeError("tool server unavailable"),
    ]
    for failure in failures:
        repository = InMemoryWorkflowRepository()
        workflow = repository.save_workflow(_workflow([_node("tests", tool_name="run_tests")]))
        gateway = SequencedGateway([failure, _ok()])
        service = WorkflowPlanningService(repository=repository, gateway_client=gateway)

        waiting = service.execute(workflow.id, role="ENGINEER")
        assert waiting.nodes[0].execution_status == WorkflowNodeStatus.RETRYING
        executed = service.resume(_make_retry_due(repository, waiting.id, "tests"), role="ENGINEER")

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


def test_waiting_approval_resume_persists_and_reuses_gateway_approval_id() -> None:
    repository = InMemoryWorkflowRepository()
    workflow = repository.save_workflow(
        _workflow([_node("restart", tool_name="restart_service", max_retries=0)])
    )
    approval_id = uuid4()
    gateway = SequencedGateway([_pending_approval(approval_id), _ok()])
    service = WorkflowPlanningService(repository=repository, gateway_client=gateway)

    waiting = service.execute(workflow.id, role="OPERATOR")
    waiting_node = waiting.nodes[0]
    assert waiting.status == WorkflowStatus.WAITING_APPROVAL
    assert waiting_node.execution_status == WorkflowNodeStatus.WAITING_APPROVAL
    assert waiting_node.approval_id == approval_id
    assert waiting_node.approval_state == WorkflowApprovalState.WAITING_APPROVAL

    resumed = service.resume(waiting.id, role="OPERATOR")
    resumed_node = resumed.nodes[0]

    assert resumed.status == WorkflowStatus.COMPLETED
    assert resumed_node.execution_status == WorkflowNodeStatus.SUCCEEDED
    assert resumed_node.approval_id == approval_id
    assert resumed_node.approval_state == WorkflowApprovalState.SUCCEEDED
    assert gateway.requests[1].approval_id == approval_id


def test_outbox_publish_unavailable_does_not_lose_checkpoint() -> None:
    repository = InMemoryWorkflowRepository()
    workflow = repository.save_workflow(_workflow([_node("ticket")]))
    publisher = InMemoryWorkflowEventPublisher(fail_publish=True)
    service = WorkflowPlanningService(
        repository=repository,
        gateway_client=SequencedGateway([_ok()]),
        event_publisher=publisher,
    )

    executed = service.execute(workflow.id, role="ENGINEER")
    pending = repository.pending_workflow_events(limit=20)
    published = service.publish_pending_events(limit=20)

    assert executed.status == WorkflowStatus.COMPLETED
    assert pending
    assert published == 0
    assert repository.pending_workflow_events(limit=20)


def test_workflow_outbox_drain_preserves_event_id_for_idempotent_consumers() -> None:
    repository = InMemoryWorkflowRepository()
    workflow = repository.save_workflow(_workflow([_node("ticket")]))
    publisher = InMemoryWorkflowEventPublisher()
    service = WorkflowPlanningService(
        repository=repository,
        gateway_client=SequencedGateway([_ok()]),
        event_publisher=publisher,
    )

    service.execute(workflow.id, role="ENGINEER")
    pending = repository.pending_workflow_events(limit=20)
    published = service.publish_pending_events(limit=20)

    assert published == len(pending)
    assert publisher.events
    assert {event.event_id for event in publisher.events} == {event.event_id for event in pending}
    assert repository.pending_workflow_events(limit=20) == []


def test_workflow_outbox_can_publish_to_kafka_topic_with_stable_event_id() -> None:
    repository = InMemoryWorkflowRepository()
    workflow = repository.save_workflow(_workflow([_node("ticket")]))
    producer = RecordingKafkaProducer()
    service = WorkflowPlanningService(
        repository=repository,
        gateway_client=SequencedGateway([_ok()]),
        event_publisher=KafkaWorkflowEventPublisher(producer),
    )

    service.execute(workflow.id, role="ENGINEER")
    pending = repository.pending_workflow_events(limit=20)
    published = service.publish_pending_events(limit=20)

    assert published == len(pending)
    assert producer.messages
    topic, payload = producer.messages[0]
    assert topic == WORKFLOW_EVENTS_TOPIC
    assert payload["event_id"] in {str(event.event_id) for event in pending}


def test_redis_unavailable_retry_and_backend_restart_recovery() -> None:
    repository = InMemoryWorkflowRepository()
    workflow = repository.save_workflow(_workflow([_node("tests", tool_name="run_tests")]))
    first_service = WorkflowPlanningService(
        repository=repository,
        gateway_client=SequencedGateway([RuntimeError("Redis unavailable")]),
    )

    waiting = first_service.execute(workflow.id, role="ENGINEER")
    assert waiting.nodes[0].execution_status == WorkflowNodeStatus.RETRYING

    second_service = WorkflowPlanningService(
        repository=repository,
        gateway_client=SequencedGateway([_ok()]),
    )
    recovered = second_service.resume(
        _make_retry_due(repository, workflow.id, "tests"),
        role="ENGINEER",
    )

    assert recovered.status == WorkflowStatus.COMPLETED
    assert recovered.nodes[0].attempts == 2


def test_gateway_wrapped_outputs_bind_typed_runtime_references() -> None:
    repository = InMemoryWorkflowRepository()
    logs = _node("logs", tool_name="get_pipeline_logs", depends_on=["failed_jobs"]).model_copy(
        update={
            "arguments": {"repository": "ImmanuelP31/MCP_AI", "job_id": 0},
            "argument_references": [
                ArgumentReference(
                    argument="job_id",
                    source_node_id="failed_jobs",
                    output_path="data.jobs.0.id",
                )
            ],
        }
    )
    workflow = repository.save_workflow(
        _workflow([_node("failed_jobs", tool_name="get_failed_jobs"), logs])
    )
    gateway = SequencedGateway(
        [
            _ok({"jobs": [{"id": 777}]}),
            _ok({"log_excerpt": "bounded failure log"}),
        ]
    )
    service = WorkflowPlanningService(repository=repository, gateway_client=gateway)

    executed = service.execute(workflow.id, role="ENGINEER")

    assert executed.status == WorkflowStatus.COMPLETED
    assert gateway.requests[1].arguments["job_id"] == 777


def test_typed_condition_reads_dependency_output_to_execute_or_skip_branch() -> None:
    for source, expected_status in [
        ("source_code_failure", WorkflowNodeStatus.SUCCEEDED),
        ("pipeline_or_environment", WorkflowNodeStatus.SKIPPED),
    ]:
        repository = InMemoryWorkflowRepository()
        issue = _node("issue", tool_name="create_issue", depends_on=["analysis"]).model_copy(
            update={
                "typed_condition": WorkflowCondition(
                    source_node_id="analysis",
                    output_path="data.source",
                    operator=ConditionOperator.EQ,
                    value="source_code_failure",
                )
            }
        )
        workflow = repository.save_workflow(
            _workflow([_node("analysis", tool_name="analyze_build_failure"), issue])
        )
        gateway = SequencedGateway([_ok({"source": source}), _ok({"issue_number": 31})])
        service = WorkflowPlanningService(repository=repository, gateway_client=gateway)

        executed = service.execute(workflow.id, role="ENGINEER")

        nodes = {node.id: node for node in executed.nodes}
        assert nodes["issue"].execution_status == expected_status


def test_resiliency_metrics_are_emitted() -> None:
    repository = InMemoryWorkflowRepository()
    workflow = repository.save_workflow(_workflow([_node("tests", tool_name="run_tests")]))
    service = WorkflowPlanningService(
        repository=repository,
        gateway_client=SequencedGateway([TimeoutError("timeout"), _ok()]),
    )

    waiting = service.execute(workflow.id, role="ENGINEER")
    service.resume(_make_retry_due(repository, waiting.id, "tests"), role="ENGINEER")

    metrics = metrics_response().decode("utf-8")
    assert "workflow_executions_total" in metrics
    assert "workflow_retries_total" in metrics
    assert "workflow_execution_duration_seconds" in metrics


def test_non_idempotent_tool_does_not_retry_just_because_workflow_id_exists() -> None:
    repository = InMemoryWorkflowRepository()
    workflow = repository.save_workflow(_workflow([_node("ticket")]))
    service = WorkflowPlanningService(
        repository=repository,
        gateway_client=SequencedGateway([TimeoutError("timeout")]),
    )

    executed = service.execute(workflow.id, role="ENGINEER")

    node = executed.nodes[0]
    assert executed.status == WorkflowStatus.FAILED
    assert node.execution_status == WorkflowNodeStatus.FAILED
    assert node.attempts == 1
    assert node.next_retry_at is None


def test_workflow_execution_forwards_verified_auth_token_to_gateway() -> None:
    repository = InMemoryWorkflowRepository()
    workflow = repository.save_workflow(_workflow([_node("tests", tool_name="run_tests")]))
    gateway = SequencedGateway([_ok()])
    service = WorkflowPlanningService(repository=repository, gateway_client=gateway)
    test_token = "verified-enterprise-jwt"  # noqa: S105  # nosec B105 - deterministic test value.

    executed = service.execute(
        workflow.id,
        role="ENGINEER",
        auth_token=test_token,
    )

    assert executed.status == WorkflowStatus.COMPLETED
    assert gateway.requests[0].auth_token == test_token


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


class RecordingKafkaProducer:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict[str, Any]]] = []

    def send(self, topic: str, value: bytes) -> object:
        import json

        decoded = json.loads(value.decode("utf-8"))
        self.messages.append((topic, decoded))
        return None


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


def _make_retry_due(
    repository: InMemoryWorkflowRepository,
    workflow_id: UUID,
    node_id: str,
) -> UUID:
    workflow = repository.get_workflow(workflow_id)
    assert workflow is not None
    nodes = [
        node.model_copy(update={"next_retry_at": datetime.now(UTC) - timedelta(seconds=1)})
        if node.id == node_id
        else node
        for node in workflow.nodes
    ]
    return repository.save_workflow(workflow.model_copy(update={"nodes": nodes})).id


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


def _ok(data: dict[str, Any] | None = None) -> GatewayToolResponse:
    return GatewayToolResponse(
        ok=True,
        decision=GatewayDecision.ALLOWED,
        correlation_id=uuid4(),
        data={"tool_result": {"ok": True, "data": data or {}}},
    )


def _pending_approval(approval_id: UUID) -> GatewayToolResponse:
    return GatewayToolResponse(
        ok=True,
        decision=GatewayDecision.PENDING_APPROVAL,
        correlation_id=uuid4(),
        data={
            "approval_id": str(approval_id),
            "approval_status": "PENDING",
            "risk_level": "HIGH",
        },
    )


def _failed(code: str, message: str) -> GatewayToolResponse:
    return GatewayToolResponse(
        ok=False,
        decision=GatewayDecision.DENIED,
        correlation_id=uuid4(),
        data={},
        error={"code": code, "message": message},
    )
