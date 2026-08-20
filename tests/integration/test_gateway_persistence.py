from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from mcp_ops_mcp_gateway.models import GatewayDecision, GatewayToolRequest
from mcp_ops_mcp_gateway.persistence import (
    GatewayPersistenceBase,
    SqlAlchemyApprovalStore,
    SqlAlchemyAuditLog,
    SqlAlchemyFixedWindowRateLimiter,
    SqlAlchemyIdempotencyStore,
)
from mcp_ops_mcp_gateway.service import McpGateway
from mcp_ops_policy.tool_registry import ToolMetadata
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def test_gateway_persistent_stores_survive_gateway_instances() -> None:
    session_factory = _session_factory()
    gateway = _gateway(session_factory)

    pending = gateway.call_tool(
        GatewayToolRequest(
            auth_token="operator-token",  # noqa: S106  # nosec B106 - deterministic test token.
            tool_name="restart_service",
            arguments={
                "device_id": "SIM-014",
                "service_name": "telemetry-agent",
                "reason": "Persistent approval store integration test.",
            },
            idempotency_key="persistent-restart-request",
        )
    )
    approval_id = UUID(str(pending.data["approval_id"]))

    gateway_reloaded = _gateway(session_factory)
    duplicate = gateway_reloaded.call_tool(
        GatewayToolRequest(
            auth_token="operator-token",  # noqa: S106  # nosec B106 - deterministic test token.
            tool_name="restart_service",
            arguments={
                "device_id": "SIM-014",
                "service_name": "telemetry-agent",
                "reason": "Persistent approval store integration test.",
            },
            idempotency_key="persistent-restart-request",
        )
    )
    detail = gateway_reloaded.get_approval("admin-token", approval_id)
    approved = gateway_reloaded.approve_operation("admin-token", approval_id)

    assert pending.decision == GatewayDecision.PENDING_APPROVAL
    assert not duplicate.ok
    assert duplicate.error is not None
    assert duplicate.error["code"] == "duplicate_operation"
    assert detail.data["approval"]["status"] == "PENDING"
    assert approved.ok
    assert len(gateway_reloaded.audit_log.records) >= 3


def test_gateway_persistent_idempotency_replays_completed_outcome() -> None:
    session_factory = _session_factory()
    gateway = _gateway(session_factory)

    first = gateway.call_tool(
        GatewayToolRequest(
            auth_token="viewer-token",  # noqa: S106  # nosec B106 - deterministic test token.
            tool_name="get_device",
            arguments={"device_id": "SIM-014"},
            idempotency_key="persistent-read-replay",
        )
    )
    replay = _gateway(session_factory).call_tool(
        GatewayToolRequest(
            auth_token="viewer-token",  # noqa: S106  # nosec B106 - deterministic test token.
            tool_name="get_device",
            arguments={"device_id": "SIM-014"},
            idempotency_key="persistent-read-replay",
        )
    )

    assert first.ok
    assert replay.ok
    assert replay.data == first.data


def test_gateway_persistent_rate_limit_is_shared_across_instances() -> None:
    session_factory = _session_factory()
    registry = dict(McpGateway().registry)
    metadata = registry["get_device_status"].model_copy(update={"rate_limit": "1/minute"})
    registry["get_device_status"] = metadata
    gateway = _gateway(session_factory, registry=registry)

    first = gateway.call_tool(
        GatewayToolRequest(
            auth_token="ai-token",  # noqa: S106  # nosec B106 - deterministic test token.
            tool_name="get_device_status",
            arguments={"device_id": "SIM-014"},
            idempotency_key="persistent-rate-1",
        )
    )
    second = _gateway(session_factory, registry=registry).call_tool(
        GatewayToolRequest(
            auth_token="ai-token",  # noqa: S106  # nosec B106 - deterministic test token.
            tool_name="get_device_status",
            arguments={"device_id": "SIM-014"},
            idempotency_key="persistent-rate-2",
        )
    )

    assert first.ok
    assert not second.ok
    assert second.error is not None
    assert second.error["code"] == "rate_limit_exceeded"


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite:///:memory:")
    GatewayPersistenceBase.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _gateway(
    session_factory: sessionmaker[Session],
    *,
    registry: dict[str, ToolMetadata] | None = None,
) -> McpGateway:
    return McpGateway(
        registry=registry,
        rate_limiter=SqlAlchemyFixedWindowRateLimiter(session_factory),
        idempotency=SqlAlchemyIdempotencyStore(session_factory),
        approvals=SqlAlchemyApprovalStore(
            session_factory,
            id_factory=lambda: UUID("22222222-2222-2222-2222-222222222222"),
        ),
        audit_log=SqlAlchemyAuditLog(session_factory),
        clock=lambda: datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
    )
