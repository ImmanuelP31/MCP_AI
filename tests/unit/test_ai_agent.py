from __future__ import annotations

from pathlib import Path
from uuid import UUID

from mcp_ops_ai_agent.evaluation import evaluate_agent
from mcp_ops_ai_agent.service import AiEngineeringAgent
from mcp_ops_mcp_gateway.models import GatewayToolRequest, GatewayToolResponse
from mcp_ops_mcp_gateway.service import McpGateway


class RecordingGatewayClient:
    def __init__(self, gateway: McpGateway) -> None:
        self.gateway = gateway
        self.requests: list[GatewayToolRequest] = []

    def call_tool(self, request: GatewayToolRequest) -> GatewayToolResponse:
        self.requests.append(request)
        return self.gateway.call_tool(request)


def test_agent_diagnoses_unhealthy_device_using_only_governed_gateway_tools() -> None:
    gateway = McpGateway()
    client = RecordingGatewayClient(gateway)
    agent = AiEngineeringAgent(gateway_client=client)

    response = agent.handle("Why is SIM-014 unhealthy?")

    assert response.ok
    assert "SIM-014" in response.message
    assert response.evidence
    assert response.data["diagnostic_report"]["possible_causes"]
    assert response.confidence >= 0.7
    assert response.escalation_required
    assert response.selected_tools
    assert response.citations
    assert [request.tool_name for request in client.requests] == [
        "get_device_status",
        "get_device_telemetry",
        "get_device_services",
        "get_recent_errors",
        "find_similar_incidents",
        "run_diagnostic_check",
        "generate_diagnostic_summary",
    ]
    assert all(request.auth_token == "ai-token" for request in client.requests)  # noqa: S105  # nosec B105
    assert len(gateway.audit_log.records) == 7


def test_agent_restart_request_creates_approval_and_does_not_execute() -> None:
    gateway = McpGateway()
    client = RecordingGatewayClient(gateway)
    agent = AiEngineeringAgent(gateway_client=client)

    response = agent.handle("Restart SIM-014 service.")
    approval_id = UUID(str(response.approval_id))
    approval = gateway.approvals.detail(approval_id, gateway.clock())

    assert response.ok
    assert response.approval_required
    assert response.data["service_name"] == "sensor-ingestor"
    assert response.data["approval_status"] == "PENDING"
    assert approval.status.value == "PENDING"
    assert approval.executed_at is None
    assert client.requests[-1].tool_name == "restart_service"
    assert client.requests[-1].approval_id is None


def test_agent_executes_restart_only_after_human_approval() -> None:
    gateway = McpGateway()
    client = RecordingGatewayClient(gateway)
    agent = AiEngineeringAgent(gateway_client=client)
    pending = agent.handle("Restart SIM-014 service.")
    approval_id = UUID(str(pending.approval_id))

    approval = gateway.approve_operation("admin-token", approval_id)
    executed = agent.handle(f"Restart SIM-014 service with approval {approval_id}.")

    assert approval.ok
    assert executed.ok
    assert executed.data["operation"] == "restart_service"
    assert client.requests[-1].approval_id == approval_id
    assert gateway.approvals.detail(approval_id, gateway.clock()).status.value == "EXECUTED"


def test_agent_reports_governance_denial_instead_of_bypassing_gateway() -> None:
    gateway = McpGateway()
    client = RecordingGatewayClient(gateway)
    agent = AiEngineeringAgent(
        gateway_client=client,
        operation_auth_token="engineer-token",  # noqa: S106  # nosec B106 - deterministic test token.
    )

    response = agent.handle("Restart SIM-014 service.")

    assert not response.ok
    assert response.data["error"]["code"] == "permission_denied"
    assert client.requests[-1].tool_name == "restart_service"
    assert not hasattr(agent, "approve_operation")


def test_agent_uses_caller_role_for_task_authorization() -> None:
    gateway = McpGateway()
    client = RecordingGatewayClient(gateway)
    agent = AiEngineeringAgent(gateway_client=client)

    response = agent.handle(
        "Create a maintenance ticket for SIM-014.",
        user_auth_token="viewer-token",  # noqa: S106  # nosec B106 - deterministic test token.
    )

    assert not response.ok
    assert response.data["error"]["code"] == "permission_denied"
    assert client.requests[-1].tool_name == "create_ticket"


def test_agent_can_create_ticket_when_role_has_permission() -> None:
    gateway = McpGateway()
    client = RecordingGatewayClient(gateway)
    agent = AiEngineeringAgent(gateway_client=client)

    response = agent.handle(
        "Create a maintenance ticket for SIM-014.",
        user_auth_token="engineer-token",  # noqa: S106  # nosec B106 - deterministic test token.
    )

    assert response.ok
    assert response.intent.value == "CREATE_TICKET"
    assert response.data["ticket"]["device_id"] == "SIM-014"
    assert client.requests[-1].tool_name == "create_ticket"


def test_agent_general_question_collects_context_through_gateway() -> None:
    gateway = McpGateway()
    client = RecordingGatewayClient(gateway)
    agent = AiEngineeringAgent(gateway_client=client)

    response = agent.handle(
        "What is the fleet health and business impact?",
        user_auth_token="viewer-token",  # noqa: S106  # nosec B106 - deterministic test token.
    )

    assert response.ok
    assert response.intent.value == "ANSWER_QUESTION"
    assert "devices" in response.data["context"]
    assert "retrieved_context" in response.data["context"]
    assert response.selected_tools[0].tool_name == "list_devices"
    assert [request.tool_name for request in client.requests] == [
        "list_devices",
        "get_open_tickets",
        "search_knowledge",
    ]


def test_agent_restart_request_respects_viewer_authorization() -> None:
    gateway = McpGateway()
    client = RecordingGatewayClient(gateway)
    agent = AiEngineeringAgent(gateway_client=client)

    response = agent.handle(
        "Restart SIM-014 service.",
        user_auth_token="viewer-token",  # noqa: S106  # nosec B106 - deterministic test token.
    )

    assert not response.ok
    assert response.data["error"]["code"] == "permission_denied"
    assert response.escalation_required
    assert client.requests[-1].tool_name == "restart_service"


def test_agent_procedure_uses_rag_citations() -> None:
    gateway = McpGateway()
    client = RecordingGatewayClient(gateway)
    agent = AiEngineeringAgent(gateway_client=client)

    response = agent.handle(
        "What procedure should I follow for SIM-014?",
        user_auth_token="viewer-token",  # noqa: S106  # nosec B106 - deterministic test token.
    )

    assert response.ok
    assert response.intent.value == "FIND_PROCEDURE"
    assert response.citations
    assert response.data["retrieved_context"]
    assert [request.tool_name for request in client.requests] == [
        "find_troubleshooting_steps",
        "search_knowledge",
    ]


def test_agent_evaluation_benchmark_reports_decision_quality() -> None:
    gateway = McpGateway()
    agent = AiEngineeringAgent(gateway_client=RecordingGatewayClient(gateway))

    result = evaluate_agent(agent)

    assert result.cases == 4
    assert result.intent_accuracy == 1.0
    assert result.tool_route_accuracy == 1.0
    assert result.outcome_accuracy == 1.0
    assert result.escalation_accuracy == 1.0
    assert result.hallucinated_tool_calls == 0
    assert result.tool_failure_rate > 0


def test_agent_package_does_not_import_forbidden_system_boundaries() -> None:
    source_root = Path(__file__).resolve().parents[1] / "services" / "ai-agent" / "src"
    forbidden = [
        "sqlalchemy",
        "psycopg",
        "redis",
        "kafka",
        "opensearch",
        "subprocess",
        "mcp_ops_simulator",
        "mcp_ops_device_mcp",
        "mcp_ops_diagnostics_mcp",
        "mcp_ops_knowledge_mcp",
        "mcp_ops_ticket_mcp",
    ]

    source_text = "\n".join(path.read_text() for path in source_root.rglob("*.py"))

    for forbidden_import in forbidden:
        assert forbidden_import not in source_text
