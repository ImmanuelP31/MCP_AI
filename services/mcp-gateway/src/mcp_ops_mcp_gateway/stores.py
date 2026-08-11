from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock, RLock
from uuid import UUID, uuid4

from mcp_ops_auth.rbac import Permission, Role, has_permission
from mcp_ops_policy.tool_registry import RiskLevel

from mcp_ops_mcp_gateway.errors import (
    ApprovalDenied,
    ApprovalNotFound,
    AuthenticationFailed,
    DuplicateOperation,
    ExpiredApproval,
    PermissionDenied,
    RateLimitExceeded,
)
from mcp_ops_mcp_gateway.models import (
    ApprovalEvent,
    ApprovalRecord,
    ApprovalStatus,
    AuditRecord,
    GatewayDecision,
    Principal,
    PrincipalType,
)


@dataclass
class TokenAuthenticator:
    _principals: dict[str, Principal] = field(
        default_factory=lambda: {
            "viewer-token": Principal(principal_id="viewer-1", role=Role.VIEWER),
            "engineer-token": Principal(principal_id="engineer-1", role=Role.ENGINEER),
            "operator-token": Principal(principal_id="operator-1", role=Role.OPERATOR),
            "admin-token": Principal(principal_id="admin-1", role=Role.ADMIN),
            "admin2-token": Principal(principal_id="admin-2", role=Role.ADMIN),
            "ai-token": Principal(
                principal_id="ai-agent-1",
                role=Role.ENGINEER,
                principal_type=PrincipalType.AI_AGENT,
            ),
            "ai-admin-token": Principal(
                principal_id="ai-admin-1",
                role=Role.ADMIN,
                principal_type=PrincipalType.AI_AGENT,
            ),
        }
    )

    def authenticate(self, token: str) -> Principal:
        try:
            return self._principals[token]
        except KeyError as exc:
            raise AuthenticationFailed("Authentication token is invalid.") from exc


class GatewayAuthorizer:
    def authorize(self, principal: Principal, required_permission: str) -> None:
        permission = Permission(required_permission)
        if not has_permission(principal.role, permission):
            raise PermissionDenied(
                f"Role {principal.role.value} lacks permission {required_permission}."
            )

    def authorize_approval(self, principal: Principal, approval: ApprovalRecord) -> None:
        self.authorize(principal, Permission.APPROVALS_APPROVE.value)
        if principal.principal_type == PrincipalType.AI_AGENT:
            raise PermissionDenied("AI principals cannot approve operations.")
        if principal.principal_id == approval.requester_id:
            raise PermissionDenied("Requesters cannot approve their own operation.")


class FixedWindowRateLimiter:
    def __init__(self) -> None:
        self._calls: dict[tuple[str, str], deque[datetime]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, principal: Principal, tool_name: str, rate_limit: str, now: datetime) -> None:
        with self._lock:
            allowed, window = _parse_rate_limit(rate_limit)
            key = (principal.principal_id, tool_name)
            calls = self._calls[key]
            while calls and now - calls[0] >= window:
                calls.popleft()
            if len(calls) >= allowed:
                raise RateLimitExceeded(f"Rate limit exceeded for {tool_name}.")
            calls.append(now)


class IdempotencyStore:
    def __init__(self, ttl_seconds: int = 3600, max_entries: int = 10000) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._keys: dict[tuple[str, str], datetime] = {}
        self._lock = Lock()

    def reserve(
        self,
        principal: Principal,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> None:
        reserved_at = now or utc_now()
        key = (principal.principal_id, idempotency_key)
        with self._lock:
            self._expire(reserved_at)
            if key in self._keys:
                raise DuplicateOperation("Duplicate operation idempotency key.")
            self._keys[key] = reserved_at
            self._evict_oldest_if_needed()

    def _expire(self, now: datetime) -> None:
        expires_before = now - timedelta(seconds=self._ttl_seconds)
        expired = [key for key, created_at in self._keys.items() if created_at <= expires_before]
        for key in expired:
            self._keys.pop(key, None)

    def _evict_oldest_if_needed(self) -> None:
        while len(self._keys) > self._max_entries:
            oldest_key = min(self._keys, key=lambda key: self._keys[key])
            self._keys.pop(oldest_key, None)


class ApprovalStore:
    def __init__(
        self,
        ttl_seconds: int = 3600,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._id_factory = id_factory
        self._approvals: dict[UUID, ApprovalRecord] = {}
        self._events: list[ApprovalEvent] = []
        self._lock = RLock()
        self._audit_log: AuditLog | None = None

    def attach_audit_log(self, audit_log: AuditLog) -> None:
        self._audit_log = audit_log

    def create(
        self,
        principal: Principal,
        tool_name: str,
        arguments: dict[str, object],
        risk_level: RiskLevel,
        now: datetime,
        *,
        workflow_id: UUID | None = None,
        workflow_node_id: str | None = None,
        arguments_hash: str | None = None,
        approval_binding_hash: str | None = None,
    ) -> ApprovalRecord:
        with self._lock:
            approval = ApprovalRecord(
                approval_id=self._id_factory(),
                requester_id=principal.principal_id,
                requester_type=principal.principal_type,
                tool_name=tool_name,
                arguments=dict(arguments),
                risk_level=risk_level,
                created_at=now,
                expires_at=now + timedelta(seconds=self._ttl_seconds),
                workflow_id=workflow_id,
                workflow_node_id=workflow_node_id,
                arguments_hash=arguments_hash,
                approval_binding_hash=approval_binding_hash,
            )
            self._approvals[approval.approval_id] = approval
            self._record_transition(
                approval,
                "approval.requested",
                principal,
                now,
                "PENDING_APPROVAL",
                "Approval request created.",
            )
            return approval

    def list_approvals(
        self,
        now: datetime,
        status: ApprovalStatus | None = None,
    ) -> list[ApprovalRecord]:
        with self._lock:
            self.expire_pending(now)
            approvals = list(self._approvals.values())
            if status is not None:
                approvals = [approval for approval in approvals if approval.status == status]
            return sorted(approvals, key=lambda approval: approval.created_at)

    def detail(self, approval_id: UUID, now: datetime) -> ApprovalRecord:
        with self._lock:
            approval = self._approval(approval_id)
            self._expire_if_needed(approval, now)
            return approval

    def events(self) -> list[ApprovalEvent]:
        with self._lock:
            return list(self._events)

    def get(self, approval_id: UUID, now: datetime) -> ApprovalRecord:
        with self._lock:
            approval = self._approval(approval_id)
            self._expire_if_needed(approval, now)
            if approval.status == ApprovalStatus.EXPIRED:
                raise ExpiredApproval("Approval has expired.")
            return approval

    def approve(self, approval_id: UUID, approver: Principal, now: datetime) -> ApprovalRecord:
        with self._lock:
            approval = self.get(approval_id, now)
            if approval.status != ApprovalStatus.PENDING:
                raise ApprovalDenied(
                    f"Approval is not pending; current status is {approval.status.value}."
                )
            approval.status = ApprovalStatus.APPROVED
            approval.approved_by = approver.principal_id
            approval.approved_at = now
            approval.version += 1
            self._record_transition(
                approval,
                "approval.approved",
                approver,
                now,
                "APPROVED",
                "Approval granted.",
            )
            return approval

    def reject(
        self,
        approval_id: UUID,
        rejector: Principal,
        reason: str,
        now: datetime,
    ) -> ApprovalRecord:
        with self._lock:
            approval = self.get(approval_id, now)
            if approval.status != ApprovalStatus.PENDING:
                raise ApprovalDenied(
                    f"Approval is not pending; current status is {approval.status.value}."
                )
            approval.status = ApprovalStatus.REJECTED
            approval.rejected_by = rejector.principal_id
            approval.rejected_at = now
            approval.failure_reason = reason
            approval.version += 1
            self._record_transition(
                approval,
                "approval.rejected",
                rejector,
                now,
                "REJECTED",
                reason,
            )
            return approval

    def expire_pending(self, now: datetime) -> None:
        with self._lock:
            for approval in self._approvals.values():
                self._expire_if_needed(approval, now)

    def mark_executed(
        self,
        approval: ApprovalRecord,
        actor: Principal,
        now: datetime,
        result: dict[str, object],
    ) -> ApprovalRecord:
        with self._lock:
            current = self.get(approval.approval_id, now)
            if current.status != ApprovalStatus.APPROVED:
                raise ApprovalDenied(
                    "Approval must be APPROVED before execution; "
                    f"current status is {current.status.value}."
                )
            current.status = ApprovalStatus.EXECUTED
            current.executed_at = now
            current.execution_result = dict(result)
            current.version += 1
            self._record_transition(
                current,
                "approval.executed",
                actor,
                now,
                "EXECUTED",
                "Approved operation executed.",
            )
            return current

    def mark_failed(
        self,
        approval: ApprovalRecord,
        actor: Principal,
        now: datetime,
        reason: str,
    ) -> ApprovalRecord:
        with self._lock:
            current = self._approval(approval.approval_id)
            if current.status not in {ApprovalStatus.APPROVED, ApprovalStatus.PENDING}:
                raise ApprovalDenied(
                    f"Approval cannot fail from current status {current.status.value}."
                )
            current.status = ApprovalStatus.FAILED
            current.failure_reason = reason
            current.version += 1
            self._record_transition(
                current,
                "approval.failed",
                actor,
                now,
                "FAILED",
                reason,
            )
            return current

    def _approval(self, approval_id: UUID) -> ApprovalRecord:
        try:
            return self._approvals[approval_id]
        except KeyError as exc:
            raise ApprovalNotFound(f"Approval {approval_id} was not found.") from exc

    def _expire_if_needed(self, approval: ApprovalRecord, now: datetime) -> None:
        if approval.status == ApprovalStatus.PENDING and now >= approval.expires_at:
            approval.status = ApprovalStatus.EXPIRED
            approval.version += 1
            actor = Principal(
                principal_id="system",
                role=Role.ADMIN,
                principal_type=PrincipalType.SERVICE,
            )
            self._record_transition(
                approval,
                "approval.expired",
                actor,
                now,
                "EXPIRED",
                "Approval expired.",
            )

    def _record_transition(
        self,
        approval: ApprovalRecord,
        event_type: str,
        actor: Principal,
        now: datetime,
        execution_status: str,
        summary: str,
    ) -> None:
        self._events.append(
            ApprovalEvent(
                approval_id=approval.approval_id,
                event_type=event_type,
                timestamp=now,
                actor_id=actor.principal_id,
                status=approval.status,
                tool_name=approval.tool_name,
            )
        )
        if self._audit_log is not None:
            self._audit_log.append(
                AuditRecord(
                    timestamp=now,
                    actor_id=actor.principal_id,
                    actor_role=actor.role,
                    tool_name=event_type,
                    correlation_id=approval.approval_id,
                    decision=GatewayDecision.ALLOWED,
                    authorization_result="ALLOW",
                    risk_level=approval.risk_level,
                    approval_status=approval.status,
                    execution_status=execution_status,
                    result_summary=summary,
                )
            )


class AuditLog:
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []
        self._lock = Lock()

    def append(self, record: AuditRecord) -> None:
        with self._lock:
            self.records.append(record)


def utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_rate_limit(rate_limit: str) -> tuple[int, timedelta]:
    count_text, window_text = rate_limit.split("/", maxsplit=1)
    count = int(count_text)
    if window_text == "minute":
        return count, timedelta(minutes=1)
    if window_text == "second":
        return count, timedelta(seconds=1)
    raise ValueError(f"Unsupported rate limit window: {rate_limit}")
