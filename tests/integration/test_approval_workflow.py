from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID

from mcp_ops_mcp_gateway.models import ApprovalStatus, GatewayDecision, GatewayToolRequest
from mcp_ops_mcp_gateway.service import McpGateway
from mcp_ops_mcp_gateway.stores import ApprovalStore


class MutableClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


def test_complete_restart_service_approval_state_machine() -> None:
    gateway = McpGateway()

    pending = gateway.call_tool(_restart_request("restart-create-1"))
    approval_id = UUID(str(pending.data["approval_id"]))
    details = gateway.get_approval("admin-token", approval_id)
    approval = gateway.approve_operation("admin-token", approval_id)
    execution = gateway.call_tool(_restart_request("restart-execute-1", approval_id=approval_id))
    final_details = gateway.get_approval("admin-token", approval_id)

    assert pending.decision == GatewayDecision.PENDING_APPROVAL
    assert details.data["approval"]["status"] == ApprovalStatus.PENDING.value
    assert approval.data["approval_status"] == ApprovalStatus.APPROVED.value
    assert execution.ok
    assert final_details.data["approval"]["status"] == ApprovalStatus.EXECUTED.value
    assert final_details.data["approval"]["execution_result"]["ok"] is True
    assert _transition_types(gateway) == [
        "approval.requested",
        "approval.approved",
        "approval.executed",
    ]


def test_rejection_blocks_execution_without_approval() -> None:
    gateway = McpGateway()
    pending = gateway.call_tool(_restart_request("reject-create-1"))
    approval_id = UUID(str(pending.data["approval_id"]))

    rejection = gateway.reject_operation("admin-token", approval_id, "Insufficient evidence.")
    execution = gateway.call_tool(_restart_request("reject-execute-1", approval_id=approval_id))

    assert rejection.ok
    assert rejection.data["approval_status"] == ApprovalStatus.REJECTED.value
    assert not execution.ok
    assert execution.error is not None
    assert execution.error["code"] == "malformed_arguments"
    assert "approval.rejected" in _transition_types(gateway)


def test_expiration_prevents_approval_and_records_transition() -> None:
    clock = MutableClock()
    gateway = McpGateway(clock=clock.now, approvals=ApprovalStore(ttl_seconds=1))
    pending = gateway.call_tool(_restart_request("expire-create-1"))
    approval_id = UUID(str(pending.data["approval_id"]))

    clock.advance(timedelta(seconds=2))
    details = gateway.get_approval("admin-token", approval_id)
    approval = gateway.approve_operation("admin-token", approval_id)

    assert details.data["approval"]["status"] == ApprovalStatus.EXPIRED.value
    assert not approval.ok
    assert approval.error is not None
    assert approval.error["code"] == "expired_approval"
    assert "approval.expired" in _transition_types(gateway)


def test_duplicate_approval_is_rejected_with_concurrency_safe_state_check() -> None:
    gateway = McpGateway()
    pending = gateway.call_tool(_restart_request("concurrent-create-1"))
    approval_id = UUID(str(pending.data["approval_id"]))

    first = gateway.approve_operation("admin-token", approval_id)
    second = gateway.approve_operation("admin2-token", approval_id)

    assert first.ok
    assert not second.ok
    assert second.error is not None
    assert second.error["code"] == "approval_denied"
    assert gateway.approvals.detail(approval_id, gateway.clock()).version == 2


def test_concurrent_approvers_cannot_both_approve_same_request() -> None:
    gateway = McpGateway()
    pending = gateway.call_tool(_restart_request("parallel-create-1"))
    approval_id = UUID(str(pending.data["approval_id"]))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda token: gateway.approve_operation(token, approval_id),
                ["admin-token", "admin2-token"],
            )
        )

    assert sum(result.ok for result in results) == 1
    assert sum(result.error is not None for result in results) == 1
    assert gateway.approvals.detail(approval_id, gateway.clock()).status == ApprovalStatus.APPROVED


def test_unauthorized_user_cannot_approve_or_reject() -> None:
    gateway = McpGateway()
    pending = gateway.call_tool(_restart_request("unauthorized-create-1"))
    approval_id = UUID(str(pending.data["approval_id"]))

    approve = gateway.approve_operation("viewer-token", approval_id)
    reject = gateway.reject_operation("viewer-token", approval_id, "Nope.")

    assert approve.error is not None
    assert approve.error["code"] == "permission_denied"
    assert reject.error is not None
    assert reject.error["code"] == "permission_denied"


def test_failed_execution_moves_approval_to_failed_and_audits_transition() -> None:
    gateway = McpGateway()
    pending = gateway.call_tool(_restart_request("failed-create-1", service_name="missing-service"))
    approval_id = UUID(str(pending.data["approval_id"]))
    gateway.approve_operation("admin-token", approval_id)

    execution = gateway.call_tool(
        _restart_request(
            "failed-execute-1",
            approval_id=approval_id,
            service_name="missing-service",
        )
    )
    details = gateway.get_approval("admin-token", approval_id)

    assert not execution.ok
    assert details.data["approval"]["status"] == ApprovalStatus.FAILED.value
    assert "approval.failed" in _transition_types(gateway)


def test_listing_approvals_returns_pending_requests() -> None:
    gateway = McpGateway()
    gateway.call_tool(_restart_request("list-create-1"))

    listing = gateway.list_approvals("admin-token")

    assert listing.ok
    assert len(listing.data["approvals"]) == 1
    assert listing.data["approvals"][0]["status"] == ApprovalStatus.PENDING.value


def _restart_request(
    idempotency_key: str,
    *,
    approval_id: UUID | None = None,
    service_name: str = "sensor-ingestor",
) -> GatewayToolRequest:
    return GatewayToolRequest(
        auth_token="operator-token",  # noqa: S106  # nosec B106 - deterministic test token.
        tool_name="restart_service",
        arguments={
            "device_id": "SIM-014",
            "service_name": service_name,
            "reason": "Approved service recovery.",
        },
        idempotency_key=idempotency_key,
        approval_id=approval_id,
    )


def _transition_types(gateway: McpGateway) -> list[str]:
    return [event.event_type for event in gateway.approvals.events()]
