from __future__ import annotations

from uuid import UUID

from mcp_ops_mcp_gateway.models import GatewayDecision, GatewayToolRequest
from mcp_ops_mcp_gateway.service import McpGateway
from mcp_ops_repository_mcp.server import create_dispatcher


def test_github_repository_mcp_reads_failed_build_in_offline_demo_mode() -> None:
    dispatcher = create_dispatcher()

    result = dispatcher.call_tool(
        "get_latest_failed_build",
        {"actor_role": "ENGINEER", "repository": "ImmanuelP31/MCP_AI"},
    )

    assert not result.is_error
    assert result.structured_content["data"]["github_configured"] is False
    assert result.structured_content["data"]["latest_failed_build"]["conclusion"] == "failure"


def test_github_issue_creation_executes_through_gateway() -> None:
    gateway = McpGateway()

    response = gateway.call_tool(
        GatewayToolRequest(
            auth_token="engineer-token",  # noqa: S106  # nosec B106 - deterministic test token.
            tool_name="create_issue",
            arguments={
                "repository": "ImmanuelP31/MCP_AI",
                "title": "Investigate failed GitHub Actions build",
                "body": "The governed workflow found a code-related build failure.",
                "labels": ["demo", "mcp"],
            },
            idempotency_key="github-create-issue-1",
        )
    )

    assert response.ok
    assert response.decision == GatewayDecision.ALLOWED
    assert response.data["tool_result"]["data"]["issue"]["number"] == 42


def test_github_workflow_rerun_requires_approval_before_execution() -> None:
    gateway = McpGateway()
    arguments = {
        "repository": "ImmanuelP31/MCP_AI",
        "run_id": 9001,
        "reason": "Approved CI rerun after investigation.",
    }

    pending = gateway.call_tool(
        GatewayToolRequest(
            auth_token="engineer-token",  # noqa: S106  # nosec B106 - deterministic test token.
            tool_name="rerun_workflow",
            arguments=arguments,
            idempotency_key="github-rerun-request-1",
        )
    )
    approval_id = UUID(pending.data["approval_id"])

    approved = gateway.approve_operation("admin-token", approval_id)  # nosec B106
    executed = gateway.call_tool(
        GatewayToolRequest(
            auth_token="engineer-token",  # noqa: S106  # nosec B106 - deterministic test token.
            tool_name="rerun_workflow",
            arguments=arguments,
            approval_id=approval_id,
            idempotency_key="github-rerun-execute-1",
        )
    )

    assert pending.decision == GatewayDecision.PENDING_APPROVAL
    assert approved.ok
    assert executed.ok
    assert executed.data["tool_result"]["data"]["rerun_requested"] is True
