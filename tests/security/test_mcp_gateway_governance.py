from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from mcp_ops_common.config import get_settings
from mcp_ops_mcp.dispatcher import McpToolDispatcher, ToolDefinition
from mcp_ops_mcp.schemas import DeviceIdInput, StructuredOutput
from mcp_ops_mcp_gateway.models import GatewayDecision, GatewayToolRequest, GatewayToolResponse
from mcp_ops_mcp_gateway.service import McpGateway
from mcp_ops_mcp_gateway.stores import ApprovalStore, IdempotencyStore
from mcp_ops_policy.tool_registry import TOOL_REGISTRY


class MutableClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


def test_production_gateway_rejects_default_demo_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("POSTGRES_PASSWORD", "enterprise-postgres-secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "enterprise-jwt-secret")
    monkeypatch.setenv("SERVICE_AUTH_SHARED_SECRET", "enterprise-service-secret")
    get_settings.cache_clear()

    try:
        with pytest.raises(RuntimeError, match="explicit production authenticator"):
            McpGateway()
    finally:
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        monkeypatch.delenv("SERVICE_AUTH_SHARED_SECRET", raising=False)
        get_settings.cache_clear()


def test_viewer_cannot_operate_devices_even_with_model_supplied_operator_role() -> None:
    gateway = McpGateway()

    response = gateway.call_tool(
        _request(
            "viewer-token",
            "restart_service",
            {
                "actor_role": "OPERATOR",
                "approval_token": "APPROVED_OPERATION_TOKEN",  # nosec B105 - deterministic test token.
                "device_id": "SIM-014",
                "service_name": "sensor-ingestor",
                "reason": "Attempted model-side privilege escalation.",
            },
        )
    )

    assert not response.ok
    assert response.error is not None
    assert response.error["code"] == "permission_denied"


def test_engineer_cannot_request_high_risk_operations() -> None:
    gateway = McpGateway()

    response = gateway.call_tool(
        _request(
            "engineer-token",
            "restart_service",
            {
                "device_id": "SIM-014",
                "service_name": "sensor-ingestor",
                "reason": "Engineer should not operate devices.",
            },
        )
    )

    assert not response.ok
    assert response.error is not None
    assert response.error["code"] == "permission_denied"


def test_operator_can_request_high_risk_but_cannot_self_approve() -> None:
    gateway = McpGateway()
    pending = _operator_restart_request(gateway)
    approval_id = UUID(str(pending.data["approval_id"]))

    approval = gateway.approve_operation("operator-token", approval_id)

    assert pending.ok
    assert pending.decision == GatewayDecision.PENDING_APPROVAL
    assert not approval.ok
    assert approval.error is not None
    assert approval.error["code"] == "permission_denied"


def test_admin_can_approve_operator_request_and_gateway_executes_after_approval() -> None:
    gateway = McpGateway()
    pending = _operator_restart_request(gateway)
    approval_id = UUID(str(pending.data["approval_id"]))

    approval = gateway.approve_operation("admin-token", approval_id)
    execution = gateway.call_tool(
        _request(
            "operator-token",
            "restart_service",
            {
                "device_id": "SIM-014",
                "service_name": "sensor-ingestor",
                "reason": "Approved service recovery.",
            },
            approval_id=approval_id,
            idempotency_key="restart-service-exec-1",
        )
    )

    assert approval.ok
    assert execution.ok
    assert execution.decision == GatewayDecision.ALLOWED
    assert execution.data["tool_result"]["data"]["operation"] == "restart_service"


def test_ai_cannot_approve_its_own_request_even_with_admin_role() -> None:
    gateway = McpGateway()
    pending = gateway.call_tool(
        _request(
            "ai-admin-token",
            "restart_service",
            {
                "device_id": "SIM-014",
                "service_name": "sensor-ingestor",
                "reason": "AI requested high-risk operation.",
            },
            idempotency_key="ai-admin-request-1",
        )
    )
    approval_id = UUID(str(pending.data["approval_id"]))

    approval = gateway.approve_operation("ai-admin-token", approval_id)

    assert pending.ok
    assert not approval.ok
    assert approval.error is not None
    assert approval.error["code"] == "permission_denied"


def test_unknown_disabled_malformed_duplicate_and_expired_requests_are_rejected() -> None:
    clock = MutableClock()
    gateway = McpGateway(
        clock=clock.now,
        approvals=ApprovalStore(ttl_seconds=1),
        disabled_tools={"get_device_status"},
    )

    unknown = gateway.call_tool(_request("viewer-token", "drop_database", {}))
    disabled = gateway.call_tool(
        _request("viewer-token", "get_device_status", {"device_id": "SIM-014"})
    )
    malformed = gateway.call_tool(_request("viewer-token", "get_device", {}))
    duplicate_first = gateway.call_tool(
        _request(
            "viewer-token",
            "get_device",
            {"device_id": "SIM-014"},
            idempotency_key="duplicate-key-1",
        )
    )
    duplicate_second = gateway.call_tool(
        _request(
            "viewer-token",
            "get_device",
            {"device_id": "SIM-014"},
            idempotency_key="duplicate-key-1",
        )
    )
    pending = gateway.call_tool(
        _request(
            "operator-token",
            "restart_service",
            {
                "device_id": "SIM-014",
                "service_name": "sensor-ingestor",
                "reason": "Approval will expire.",
            },
            idempotency_key="expire-request-1",
        )
    )
    clock.advance(timedelta(seconds=2))
    expired = gateway.approve_operation("admin-token", UUID(str(pending.data["approval_id"])))

    assert unknown.error is not None
    assert unknown.error["code"] == "unknown_tool"
    assert disabled.error is not None
    assert disabled.error["code"] == "tool_disabled"
    assert malformed.error is not None
    assert malformed.error["code"] == "malformed_arguments"
    assert duplicate_first.ok
    assert duplicate_second.ok
    assert duplicate_second.data == duplicate_first.data
    assert expired.error is not None
    assert expired.error["code"] == "expired_approval"


def test_pending_approval_idempotency_key_is_not_replayed_as_execution_success() -> None:
    gateway = McpGateway()

    first = gateway.call_tool(
        _request(
            "operator-token",
            "restart_service",
            {
                "device_id": "SIM-014",
                "service_name": "sensor-ingestor",
                "reason": "Hold pending approval.",
            },
            idempotency_key="pending-replay-1",
        )
    )
    second = gateway.call_tool(
        _request(
            "operator-token",
            "restart_service",
            {
                "device_id": "SIM-014",
                "service_name": "sensor-ingestor",
                "reason": "Hold pending approval.",
            },
            idempotency_key="pending-replay-1",
        )
    )

    assert first.decision == GatewayDecision.PENDING_APPROVAL
    assert second.error is not None
    assert second.error["code"] == "duplicate_operation"


def test_requests_exceeding_rate_limits_are_rejected() -> None:
    registry = {
        name: metadata.model_copy(update={"rate_limit": "1/minute"})
        for name, metadata in TOOL_REGISTRY.items()
    }
    gateway = McpGateway(registry=registry)

    first = gateway.call_tool(_request("viewer-token", "get_device", {"device_id": "SIM-014"}))
    second = gateway.call_tool(
        _request(
            "viewer-token",
            "get_device",
            {"device_id": "SIM-014"},
            idempotency_key="rate-limit-key-2",
        )
    )

    assert first.ok
    assert second.error is not None
    assert second.error["code"] == "rate_limit_exceeded"


def test_timeout_enforcement_denies_slow_tool_execution() -> None:
    def slow_handler(_model: DeviceIdInput) -> StructuredOutput:
        time.sleep(3)
        return StructuredOutput(ok=True, data={"should_not": "complete_before_deadline"})

    registry = {
        name: metadata.model_copy(update={"timeout_seconds": 1})
        for name, metadata in TOOL_REGISTRY.items()
    }
    gateway = McpGateway(registry=registry, execution_isolation="thread")
    gateway._dispatchers["device"] = McpToolDispatcher(  # noqa: SLF001 - verifies gateway deadline.
        [
            ToolDefinition(
                registry["get_device"],
                DeviceIdInput,
                StructuredOutput,
                slow_handler,
            )
        ]
    )

    started = time.perf_counter()
    response = gateway.call_tool(_request("viewer-token", "get_device", {"device_id": "SIM-014"}))
    elapsed = time.perf_counter() - started

    assert response.error is not None
    assert response.error["code"] == "timeout"
    assert elapsed < 2


def test_process_isolated_gateway_execution_returns_structured_results() -> None:
    gateway = McpGateway(execution_isolation="process")

    response = gateway.call_tool(_request("viewer-token", "get_device", {"device_id": "SIM-014"}))

    assert response.ok
    assert response.data["tool_result"]["data"]["device"]["device_id"] == "SIM-014"


def test_audit_records_are_written_for_allowed_and_denied_requests() -> None:
    gateway = McpGateway()

    allowed = gateway.call_tool(_request("viewer-token", "get_device", {"device_id": "SIM-014"}))
    denied = gateway.call_tool(
        _request(
            "viewer-token",
            "restart_service",
            {
                "device_id": "SIM-014",
                "service_name": "sensor-ingestor",
                "reason": "Viewer cannot operate.",
            },
            idempotency_key="audit-denied-1",
        )
    )

    assert allowed.ok
    assert not denied.ok
    assert len(gateway.audit_log.records) == 2
    assert gateway.audit_log.records[0].authorization_result == "ALLOW"
    assert gateway.audit_log.records[1].authorization_result == "DENY"


def test_malformed_high_risk_arguments_do_not_create_approval() -> None:
    gateway = McpGateway()

    response = gateway.call_tool(
        _request(
            "operator-token",
            "update_device_configuration",
            {
                "device_id": "SIM-014",
                "configuration_patch": {"sql": "DROP TABLE devices"},
                "reason": "Attempted unsafe configuration patch.",
            },
            idempotency_key="bad-config-request-1",
        )
    )
    approvals = gateway.list_approvals("admin-token")

    assert not response.ok
    assert response.error is not None
    assert response.error["code"] == "malformed_arguments"
    assert approvals.data["approvals"] == []


def test_approved_operation_cannot_be_replayed_with_different_arguments() -> None:
    gateway = McpGateway()
    pending = _operator_restart_request(gateway)
    approval_id = UUID(str(pending.data["approval_id"]))
    gateway.approve_operation("admin-token", approval_id)

    replay = gateway.call_tool(
        _request(
            "operator-token",
            "restart_service",
            {
                "device_id": "SIM-014",
                "service_name": "telemetry-agent",
                "reason": "Attempted approval argument substitution.",
            },
            approval_id=approval_id,
            idempotency_key="restart-service-replay-1",
        )
    )
    details = gateway.get_approval("admin-token", approval_id)

    assert not replay.ok
    assert replay.error is not None
    assert replay.error["code"] == "malformed_arguments"
    assert details.data["approval"]["status"] == "APPROVED"


def test_idempotency_keys_expire_after_retention_window() -> None:
    clock = MutableClock()
    gateway = McpGateway(
        clock=clock.now,
        idempotency=IdempotencyStore(ttl_seconds=1, max_entries=10),
    )

    first = gateway.call_tool(
        _request(
            "viewer-token",
            "get_device",
            {"device_id": "SIM-014"},
            idempotency_key="ttl-key-1",
        )
    )
    duplicate = gateway.call_tool(
        _request(
            "viewer-token",
            "get_device",
            {"device_id": "SIM-014"},
            idempotency_key="ttl-key-1",
        )
    )
    clock.advance(timedelta(seconds=2))
    after_expiry = gateway.call_tool(
        _request(
            "viewer-token",
            "get_device",
            {"device_id": "SIM-014"},
            idempotency_key="ttl-key-1",
        )
    )

    assert first.ok
    assert duplicate.ok
    assert duplicate.data == first.data
    assert after_expiry.ok


def _operator_restart_request(gateway: McpGateway) -> GatewayToolResponse:
    return gateway.call_tool(
        _request(
            "operator-token",
            "restart_service",
            {
                "device_id": "SIM-014",
                "service_name": "sensor-ingestor",
                "reason": "Approved service recovery.",
            },
            idempotency_key="restart-service-request-1",
        )
    )


def _request(
    auth_token: str,
    tool_name: str,
    arguments: dict[str, object],
    *,
    idempotency_key: str | None = None,
    approval_id: UUID | None = None,
) -> GatewayToolRequest:
    return GatewayToolRequest(
        auth_token=auth_token,
        tool_name=tool_name,
        arguments=arguments,
        idempotency_key=idempotency_key or f"{tool_name}-key",
        approval_id=approval_id,
    )
