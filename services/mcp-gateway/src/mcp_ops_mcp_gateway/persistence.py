from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from mcp_ops_auth.rbac import Role
from mcp_ops_policy.tool_registry import RiskLevel
from sqlalchemy import DateTime, Integer, String, delete, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.types import JSON

from mcp_ops_mcp_gateway.errors import (
    ApprovalDenied,
    ApprovalNotFound,
    DuplicateOperation,
    ExpiredApproval,
    RateLimitExceeded,
)
from mcp_ops_mcp_gateway.models import (
    ApprovalEvent,
    ApprovalRecord,
    ApprovalStatus,
    AuditRecord,
    GatewayDecision,
    GatewayToolResponse,
    Principal,
    PrincipalType,
)
from mcp_ops_mcp_gateway.stores import IdempotencyOperationStatus


class GatewayPersistenceBase(DeclarativeBase):
    pass


class GatewayApprovalRow(GatewayPersistenceBase):
    __tablename__ = "gateway_approvals"

    approval_id: Mapped[UUID] = mapped_column(primary_key=True)
    requester_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    requester_type: Mapped[str] = mapped_column(String(32), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    approved_by: Mapped[str | None] = mapped_column(String(160))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_by: Mapped[str | None] = mapped_column(String(160))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(String(500))
    execution_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    workflow_id: Mapped[UUID | None] = mapped_column(nullable=True)
    workflow_node_id: Mapped[str | None] = mapped_column(String(120))
    arguments_hash: Mapped[str | None] = mapped_column(String(128))
    approval_binding_hash: Mapped[str | None] = mapped_column(String(128))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class GatewayApprovalEventRow(GatewayPersistenceBase):
    __tablename__ = "gateway_approval_events"

    event_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    approval_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)


class GatewayAuditRow(GatewayPersistenceBase):
    __tablename__ = "gateway_audit_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    actor_role: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    correlation_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    authorization_result: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_level: Mapped[str | None] = mapped_column(String(32))
    approval_status: Mapped[str | None] = mapped_column(String(32))
    execution_status: Mapped[str] = mapped_column(String(64), nullable=False)
    result_summary: Mapped[str] = mapped_column(String(500), nullable=False)
    argument_hash: Mapped[str | None] = mapped_column(String(128))
    target_resource: Mapped[str | None] = mapped_column(String(240), index=True)


class GatewayIdempotencyRow(GatewayPersistenceBase):
    __tablename__ = "gateway_idempotency_keys"

    principal_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=IdempotencyOperationStatus.RESERVED.value,
    )
    response_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class GatewayRateLimitRow(GatewayPersistenceBase):
    __tablename__ = "gateway_rate_limit_calls"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    principal_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    called_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class SqlAlchemyIdempotencyStore:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        ttl_seconds: int = 3600,
        max_entries: int = 10000,
    ) -> None:
        self.session_factory = session_factory
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries

    def reserve(
        self,
        principal: Principal,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> GatewayToolResponse | None:
        reserved_at = now or datetime.now().astimezone()
        expires_before = reserved_at - timedelta(seconds=self.ttl_seconds)
        with self.session_factory() as session:
            session.execute(
                delete(GatewayIdempotencyRow).where(
                    GatewayIdempotencyRow.created_at <= expires_before
                )
            )
            existing = session.get(
                GatewayIdempotencyRow,
                (principal.principal_id, idempotency_key),
            )
            if existing is not None:
                if (
                    existing.status
                    in {
                        IdempotencyOperationStatus.SUCCEEDED.value,
                        IdempotencyOperationStatus.TRANSIENT_FAILED.value,
                        IdempotencyOperationStatus.PERMANENT_FAILED.value,
                    }
                    and existing.response_json
                ):
                    return _response_from_json(existing.response_json)
                session.rollback()
                raise DuplicateOperation("Duplicate operation idempotency key.")
            session.add(
                GatewayIdempotencyRow(
                    principal_id=principal.principal_id,
                    idempotency_key=idempotency_key,
                    created_at=reserved_at,
                    status=IdempotencyOperationStatus.RESERVED.value,
                )
            )
            count = session.scalar(select(func.count()).select_from(GatewayIdempotencyRow)) or 0
            if count > self.max_entries:
                overflow = count - self.max_entries
                old_keys = session.scalars(
                    select(GatewayIdempotencyRow)
                    .order_by(GatewayIdempotencyRow.created_at)
                    .limit(overflow)
                ).all()
                for row in old_keys:
                    session.delete(row)
            session.commit()
            return None

    def mark_running(
        self,
        principal: Principal,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> None:
        del now
        with self.session_factory() as session:
            row = session.get(GatewayIdempotencyRow, (principal.principal_id, idempotency_key))
            if row is not None:
                row.status = IdempotencyOperationStatus.RUNNING.value
                session.commit()

    def complete(
        self,
        principal: Principal,
        idempotency_key: str,
        response: GatewayToolResponse,
        *,
        status: IdempotencyOperationStatus | None = None,
        now: datetime | None = None,
    ) -> None:
        completed_at = now or datetime.now().astimezone()
        terminal_status = status or (
            IdempotencyOperationStatus.SUCCEEDED
            if response.ok
            else IdempotencyOperationStatus.PERMANENT_FAILED
        )
        with self.session_factory() as session:
            row = session.get(GatewayIdempotencyRow, (principal.principal_id, idempotency_key))
            if row is None:
                row = GatewayIdempotencyRow(
                    principal_id=principal.principal_id,
                    idempotency_key=idempotency_key,
                    created_at=completed_at,
                )
                session.add(row)
            row.status = terminal_status.value
            row.response_json = response.model_dump(mode="json")
            session.commit()


def _response_from_json(payload: dict[str, Any]) -> GatewayToolResponse:
    coerced = dict(payload)
    if isinstance(coerced.get("decision"), str):
        coerced["decision"] = GatewayDecision(coerced["decision"])
    if isinstance(coerced.get("correlation_id"), str):
        coerced["correlation_id"] = UUID(coerced["correlation_id"])
    return GatewayToolResponse.model_validate(coerced)


class SqlAlchemyFixedWindowRateLimiter:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def check(self, principal: Principal, tool_name: str, rate_limit: str, now: datetime) -> None:
        allowed, window = _parse_rate_limit(rate_limit)
        window_start = now - window
        with self.session_factory() as session:
            session.execute(
                delete(GatewayRateLimitRow).where(GatewayRateLimitRow.called_at <= window_start)
            )
            count = (
                session.scalar(
                    select(func.count())
                    .select_from(GatewayRateLimitRow)
                    .where(GatewayRateLimitRow.principal_id == principal.principal_id)
                    .where(GatewayRateLimitRow.tool_name == tool_name)
                    .where(GatewayRateLimitRow.called_at > window_start)
                )
                or 0
            )
            if count >= allowed:
                session.rollback()
                raise RateLimitExceeded(f"Rate limit exceeded for {tool_name}.")
            session.add(
                GatewayRateLimitRow(
                    principal_id=principal.principal_id,
                    tool_name=tool_name,
                    called_at=now,
                )
            )
            session.commit()


class SqlAlchemyAuditLog:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def append(self, record: AuditRecord) -> None:
        with self.session_factory() as session:
            session.add(_audit_row(record))
            session.commit()

    @property
    def records(self) -> list[AuditRecord]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(GatewayAuditRow).order_by(GatewayAuditRow.timestamp, GatewayAuditRow.id)
            ).all()
            return [_audit_record(row) for row in rows]


class SqlAlchemyApprovalStore:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        ttl_seconds: int = 3600,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self.session_factory = session_factory
        self.ttl_seconds = ttl_seconds
        self.id_factory = id_factory
        self._audit_log: SqlAlchemyAuditLog | None = None

    def attach_audit_log(self, audit_log: SqlAlchemyAuditLog) -> None:
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
        approval = ApprovalRecord(
            approval_id=self.id_factory(),
            requester_id=principal.principal_id,
            requester_type=principal.principal_type,
            tool_name=tool_name,
            arguments=dict(arguments),
            risk_level=risk_level,
            created_at=now,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
            workflow_id=workflow_id,
            workflow_node_id=workflow_node_id,
            arguments_hash=arguments_hash,
            approval_binding_hash=approval_binding_hash,
        )
        with self.session_factory() as session:
            session.add(_approval_row(approval))
            session.add(_event_row(approval, "approval.requested", principal, now))
            session.commit()
        self._audit_transition(
            approval,
            principal,
            now,
            "approval.requested",
            "PENDING_APPROVAL",
            "Approval request created.",
        )
        return approval

    def list_approvals(
        self,
        now: datetime,
        status: ApprovalStatus | None = None,
    ) -> list[ApprovalRecord]:
        self.expire_pending(now)
        with self.session_factory() as session:
            statement = select(GatewayApprovalRow).order_by(GatewayApprovalRow.created_at)
            if status is not None:
                statement = statement.where(GatewayApprovalRow.status == status.value)
            return [_approval_record(row) for row in session.scalars(statement).all()]

    def detail(self, approval_id: UUID, now: datetime) -> ApprovalRecord:
        self._expire_if_needed(approval_id, now)
        return self._approval_record(approval_id)

    def events(self) -> list[ApprovalEvent]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(GatewayApprovalEventRow).order_by(GatewayApprovalEventRow.timestamp)
            ).all()
            return [_approval_event(row) for row in rows]

    def get(self, approval_id: UUID, now: datetime) -> ApprovalRecord:
        self._expire_if_needed(approval_id, now)
        approval = self._approval_record(approval_id)
        if approval.status == ApprovalStatus.EXPIRED:
            raise ExpiredApproval("Approval has expired.")
        return approval

    def approve(self, approval_id: UUID, approver: Principal, now: datetime) -> ApprovalRecord:
        approval = self._transition_pending(approval_id, approver, now, ApprovalStatus.APPROVED)
        approval.approved_by = approver.principal_id
        approval.approved_at = now
        self._save_record(approval, "approval.approved", approver, now)
        self._audit_transition(
            approval,
            approver,
            now,
            "approval.approved",
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
        approval = self._transition_pending(approval_id, rejector, now, ApprovalStatus.REJECTED)
        approval.rejected_by = rejector.principal_id
        approval.rejected_at = now
        approval.failure_reason = reason
        self._save_record(approval, "approval.rejected", rejector, now)
        self._audit_transition(approval, rejector, now, "approval.rejected", "REJECTED", reason)
        return approval

    def expire_pending(self, now: datetime) -> None:
        with self.session_factory() as session:
            rows = session.scalars(
                select(GatewayApprovalRow)
                .where(GatewayApprovalRow.status == ApprovalStatus.PENDING.value)
                .where(GatewayApprovalRow.expires_at <= now)
            ).all()
            for row in rows:
                row.status = ApprovalStatus.EXPIRED.value
                row.version += 1
                approval = _approval_record(row)
                actor = Principal(
                    principal_id="system",
                    role=Role.ADMIN,
                    principal_type=PrincipalType.SERVICE,
                )
                session.add(_event_row(approval, "approval.expired", actor, now))
            session.commit()

    def mark_executed(
        self,
        approval: ApprovalRecord,
        actor: Principal,
        now: datetime,
        result: dict[str, object],
    ) -> ApprovalRecord:
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
        self._save_record(current, "approval.executed", actor, now)
        self._audit_transition(
            current,
            actor,
            now,
            "approval.executed",
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
        current = self._approval_record(approval.approval_id)
        if current.status not in {ApprovalStatus.APPROVED, ApprovalStatus.PENDING}:
            raise ApprovalDenied(
                f"Approval cannot fail from current status {current.status.value}."
            )
        current.status = ApprovalStatus.FAILED
        current.failure_reason = reason
        current.version += 1
        self._save_record(current, "approval.failed", actor, now)
        self._audit_transition(current, actor, now, "approval.failed", "FAILED", reason)
        return current

    def _transition_pending(
        self,
        approval_id: UUID,
        actor: Principal,
        now: datetime,
        status: ApprovalStatus,
    ) -> ApprovalRecord:
        del actor
        approval = self.get(approval_id, now)
        if approval.status != ApprovalStatus.PENDING:
            raise ApprovalDenied(
                f"Approval is not pending; current status is {approval.status.value}."
            )
        approval.status = status
        approval.version += 1
        return approval

    def _save_record(
        self,
        approval: ApprovalRecord,
        event_type: str,
        actor: Principal,
        now: datetime,
    ) -> None:
        with self.session_factory() as session:
            row = _approval_row(approval)
            session.merge(row)
            session.add(_event_row(approval, event_type, actor, now))
            session.commit()

    def _expire_if_needed(self, approval_id: UUID, now: datetime) -> None:
        with self.session_factory() as session:
            row = session.get(GatewayApprovalRow, approval_id)
            if row is None:
                raise ApprovalNotFound(f"Approval {approval_id} was not found.")
            if row.status == ApprovalStatus.PENDING.value and now >= _aware(row.expires_at):
                row.status = ApprovalStatus.EXPIRED.value
                row.version += 1
                actor = Principal(
                    principal_id="system",
                    role=Role.ADMIN,
                    principal_type=PrincipalType.SERVICE,
                )
                session.add(_event_row(_approval_record(row), "approval.expired", actor, now))
            session.commit()

    def _approval_record(self, approval_id: UUID) -> ApprovalRecord:
        with self.session_factory() as session:
            row = session.get(GatewayApprovalRow, approval_id)
            if row is None:
                raise ApprovalNotFound(f"Approval {approval_id} was not found.")
            return _approval_record(row)

    def _audit_transition(
        self,
        approval: ApprovalRecord,
        actor: Principal,
        now: datetime,
        event_type: str,
        execution_status: str,
        summary: str,
    ) -> None:
        if self._audit_log is None:
            return
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


def _approval_row(approval: ApprovalRecord) -> GatewayApprovalRow:
    return GatewayApprovalRow(
        approval_id=approval.approval_id,
        requester_id=approval.requester_id,
        requester_type=approval.requester_type.value,
        tool_name=approval.tool_name,
        arguments=approval.arguments,
        risk_level=approval.risk_level.value,
        status=approval.status.value,
        created_at=approval.created_at,
        expires_at=approval.expires_at,
        approved_by=approval.approved_by,
        approved_at=approval.approved_at,
        rejected_by=approval.rejected_by,
        rejected_at=approval.rejected_at,
        executed_at=approval.executed_at,
        failure_reason=approval.failure_reason,
        execution_result=approval.execution_result,
        workflow_id=approval.workflow_id,
        workflow_node_id=approval.workflow_node_id,
        arguments_hash=approval.arguments_hash,
        approval_binding_hash=approval.approval_binding_hash,
        version=approval.version,
    )


def _approval_record(row: GatewayApprovalRow) -> ApprovalRecord:
    return ApprovalRecord(
        approval_id=row.approval_id,
        requester_id=row.requester_id,
        requester_type=PrincipalType(row.requester_type),
        tool_name=row.tool_name,
        arguments=row.arguments,
        risk_level=RiskLevel(row.risk_level),
        status=ApprovalStatus(row.status),
        created_at=_aware(row.created_at),
        expires_at=_aware(row.expires_at),
        approved_by=row.approved_by,
        approved_at=_aware(row.approved_at) if row.approved_at else None,
        rejected_by=row.rejected_by,
        rejected_at=_aware(row.rejected_at) if row.rejected_at else None,
        executed_at=_aware(row.executed_at) if row.executed_at else None,
        failure_reason=row.failure_reason,
        execution_result=row.execution_result,
        workflow_id=row.workflow_id,
        workflow_node_id=row.workflow_node_id,
        arguments_hash=row.arguments_hash,
        approval_binding_hash=row.approval_binding_hash,
        version=row.version,
    )


def _event_row(
    approval: ApprovalRecord,
    event_type: str,
    actor: Principal,
    now: datetime,
) -> GatewayApprovalEventRow:
    return GatewayApprovalEventRow(
        event_id=uuid4(),
        approval_id=approval.approval_id,
        event_type=event_type,
        timestamp=now,
        actor_id=actor.principal_id,
        status=approval.status.value,
        tool_name=approval.tool_name,
    )


def _approval_event(row: GatewayApprovalEventRow) -> ApprovalEvent:
    return ApprovalEvent(
        event_id=row.event_id,
        approval_id=row.approval_id,
        event_type=row.event_type,
        timestamp=_aware(row.timestamp),
        actor_id=row.actor_id,
        status=ApprovalStatus(row.status),
        tool_name=row.tool_name,
    )


def _audit_row(record: AuditRecord) -> GatewayAuditRow:
    return GatewayAuditRow(
        timestamp=record.timestamp,
        actor_id=record.actor_id,
        actor_role=record.actor_role.value,
        tool_name=record.tool_name,
        correlation_id=record.correlation_id,
        decision=record.decision.value,
        authorization_result=record.authorization_result,
        risk_level=record.risk_level.value if record.risk_level else None,
        approval_status=record.approval_status.value if record.approval_status else None,
        execution_status=record.execution_status,
        result_summary=record.result_summary,
        argument_hash=record.argument_hash,
        target_resource=record.target_resource,
    )


def _audit_record(row: GatewayAuditRow) -> AuditRecord:
    return AuditRecord(
        timestamp=_aware(row.timestamp),
        actor_id=row.actor_id,
        actor_role=Role(row.actor_role),
        tool_name=row.tool_name,
        correlation_id=row.correlation_id,
        decision=GatewayDecision(row.decision),
        authorization_result=row.authorization_result,
        risk_level=RiskLevel(row.risk_level) if row.risk_level else None,
        approval_status=ApprovalStatus(row.approval_status) if row.approval_status else None,
        execution_status=row.execution_status,
        result_summary=row.result_summary,
        argument_hash=row.argument_hash,
        target_resource=row.target_resource,
    )


def _parse_rate_limit(rate_limit: str) -> tuple[int, timedelta]:
    count_text, window_text = rate_limit.split("/", maxsplit=1)
    count = int(count_text)
    if window_text == "minute":
        return count, timedelta(minutes=1)
    if window_text == "second":
        return count, timedelta(seconds=1)
    raise ValueError(f"Unsupported rate limit window: {rate_limit}")


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
