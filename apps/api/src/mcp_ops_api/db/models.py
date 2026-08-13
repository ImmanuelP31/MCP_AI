from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship
from sqlalchemy.types import JSON

from mcp_ops_api.db.base import Base

JsonDict = dict[str, Any]


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class UuidPkMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class VersionedMixin:
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:
        return {"version_id_col": cls.version}


class UserModel(UuidPkMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'DISABLED', 'LOCKED')", name="user_status"),
        Index("ix_users_status", "status"),
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )

    role_links: Mapped[list[UserRoleModel]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    roles: Mapped[list[RoleModel]] = relationship(
        secondary="user_roles", back_populates="users", viewonly=True
    )
    assigned_tickets: Mapped[list[TicketModel]] = relationship(
        back_populates="assignee_user", foreign_keys="TicketModel.assignee_id"
    )
    created_tickets: Mapped[list[TicketModel]] = relationship(
        back_populates="created_by_user", foreign_keys="TicketModel.created_by_id"
    )


class RoleModel(UuidPkMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    user_links: Mapped[list[UserRoleModel]] = relationship(
        back_populates="role", cascade="all, delete-orphan", passive_deletes=True
    )
    permission_links: Mapped[list[RolePermissionModel]] = relationship(
        back_populates="role", cascade="all, delete-orphan", passive_deletes=True
    )
    users: Mapped[list[UserModel]] = relationship(
        secondary="user_roles", back_populates="roles", viewonly=True
    )
    permissions: Mapped[list[PermissionModel]] = relationship(
        secondary="role_permissions", back_populates="roles", viewonly=True
    )


class PermissionModel(UuidPkMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "permissions"

    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    role_links: Mapped[list[RolePermissionModel]] = relationship(
        back_populates="permission", cascade="all, delete-orphan", passive_deletes=True
    )
    roles: Mapped[list[RoleModel]] = relationship(
        secondary="role_permissions", back_populates="permissions", viewonly=True
    )


class UserRoleModel(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )

    user: Mapped[UserModel] = relationship(back_populates="role_links")
    role: Mapped[RoleModel] = relationship(back_populates="user_links")


class RolePermissionModel(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_permission"),
    )

    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False
    )

    role: Mapped[RoleModel] = relationship(back_populates="permission_links")
    permission: Mapped[PermissionModel] = relationship(back_populates="role_links")


class DeviceModel(UuidPkMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "devices"
    __table_args__ = (
        CheckConstraint(
            "status IN ('HEALTHY', 'WARNING', 'CRITICAL', 'OFFLINE')", name="device_status"
        ),
        CheckConstraint(
            "health_score >= 0 AND health_score <= 100", name="device_health_score_range"
        ),
        Index("idx_devices_status", "status"),
        Index("idx_devices_site_status", "site", "status"),
    )
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    serial_number: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    site: Mapped[str] = mapped_column(String(200), nullable=False)
    firmware_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    health_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    services: Mapped[list[DeviceServiceModel]] = relationship(
        back_populates="device", cascade="all, delete-orphan", passive_deletes=True
    )
    telemetry: Mapped[list[TelemetryModel]] = relationship(
        back_populates="device", cascade="all, delete-orphan", passive_deletes=True
    )
    alerts: Mapped[list[AlertModel]] = relationship(
        back_populates="device", cascade="all, delete-orphan", passive_deletes=True
    )
    incidents: Mapped[list[IncidentModel]] = relationship(
        back_populates="device", cascade="all, delete-orphan", passive_deletes=True
    )


class DeviceServiceModel(UuidPkMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "device_services"
    __table_args__ = (
        UniqueConstraint("device_id", "service_name", name="uq_device_services_device_service"),
        CheckConstraint(
            "status IN ('RUNNING', 'DEGRADED', 'STOPPED', 'CRASHED')", name="service_status"
        ),
        Index("idx_device_services_device_status", "device_id", "status"),
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    service_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    service_version: Mapped[str] = mapped_column(String(64), nullable=False)
    last_restart_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    device: Mapped[DeviceModel] = relationship(back_populates="services")


class TelemetryModel(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "telemetry"
    __table_args__ = (
        CheckConstraint("cpu_percent >= 0 AND cpu_percent <= 100", name="telemetry_cpu_range"),
        CheckConstraint(
            "memory_percent >= 0 AND memory_percent <= 100", name="telemetry_memory_range"
        ),
        CheckConstraint(
            "packet_loss_percent >= 0 AND packet_loss_percent <= 100",
            name="telemetry_packet_loss_range",
        ),
        CheckConstraint(
            "temperature_c >= -40 AND temperature_c <= 125", name="telemetry_temperature_range"
        ),
        CheckConstraint("disk_percent >= 0 AND disk_percent <= 100", name="telemetry_disk_range"),
        Index("idx_telemetry_device_timestamp", "device_id", "timestamp"),
    )

    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cpu_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    memory_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    network_latency_ms: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    packet_loss_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    temperature_c: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    uptime_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    disk_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)

    device: Mapped[DeviceModel] = relationship(back_populates="telemetry")


class AlertModel(UuidPkMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint("severity IN ('INFO', 'WARNING', 'CRITICAL')", name="alert_severity"),
        Index("idx_alerts_device_timestamp", "device_id", "timestamp"),
        Index("idx_alerts_severity_timestamp", "severity", "timestamp"),
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by_id: Mapped[uuid.UUID | None] = mapped_column(
        "acknowledged_by", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    device: Mapped[DeviceModel] = relationship(back_populates="alerts")


class IncidentModel(UuidPkMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')", name="incident_severity"
        ),
        CheckConstraint(
            "status IN ('OPEN', 'INVESTIGATING', 'MITIGATED', 'RESOLVED')", name="incident_status"
        ),
        Index("idx_incidents_device_created_at", "device_id", "created_at"),
        Index("idx_incidents_status_created_at", "status", "created_at"),
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    device: Mapped[DeviceModel] = relationship(back_populates="incidents")
    events: Mapped[list[IncidentEventModel]] = relationship(
        back_populates="incident", cascade="all, delete-orphan", passive_deletes=True
    )
    tickets: Mapped[list[TicketModel]] = relationship(back_populates="incident")


class IncidentEventModel(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "incident_events"
    __table_args__ = (Index("idx_incident_events_incident_timestamp", "incident_id", "timestamp"),)

    incident_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[JsonDict] = mapped_column(JSON, nullable=False, default=dict)

    incident: Mapped[IncidentModel] = relationship(back_populates="events")


class DiagnosticRunModel(UuidPkMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "diagnostic_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('REQUESTED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="diagnostic_status",
        ),
        Index("idx_diagnostic_runs_device_started_at", "device_id", "started_at"),
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        "requested_by",
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[JsonDict] = mapped_column(JSON, nullable=False, default=dict)

    device: Mapped[DeviceModel] = relationship()
    requested_by_user: Mapped[UserModel] = relationship()


class TicketModel(UuidPkMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')", name="ticket_priority"
        ),
        CheckConstraint(
            "status IN ('OPEN', 'IN_PROGRESS', 'BLOCKED', 'RESOLVED', 'CLOSED')",
            name="ticket_status",
        ),
        Index("idx_tickets_status_priority", "status", "priority"),
        Index("idx_tickets_device_created_at", "device_id", "created_at"),
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL")
    )
    priority: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        "assignee", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    team: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        "created_by",
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    related_incident_id: Mapped[uuid.UUID | None] = mapped_column(
        "related_incident", Uuid(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL")
    )
    diagnostic_evidence: Mapped[JsonDict] = mapped_column(JSON, nullable=False, default=dict)

    device: Mapped[DeviceModel | None] = relationship()
    incident: Mapped[IncidentModel | None] = relationship(back_populates="tickets")
    assignee_user: Mapped[UserModel | None] = relationship(
        back_populates="assigned_tickets", foreign_keys=[assignee_id]
    )
    created_by_user: Mapped[UserModel] = relationship(
        back_populates="created_tickets", foreign_keys=[created_by_id]
    )


class ApprovalModel(UuidPkMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint("risk_level IN ('HIGH', 'CRITICAL')", name="approval_risk_level"),
        CheckConstraint(
            "state IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED', 'EXECUTED', 'FAILED')",
            name="approval_state",
        ),
        Index("idx_approvals_state_expires_at", "state", "expires_at"),
        Index("idx_approvals_requested_by_created_at", "requested_by", "created_at"),
    )
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, unique=True)
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        "requested_by",
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    arguments: Mapped[JsonDict] = mapped_column(JSON, nullable=False, default=dict)
    target_device_id: Mapped[uuid.UUID | None] = mapped_column(
        "target_device", Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL")
    )
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        "approved_by", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_result: Mapped[JsonDict | None] = mapped_column(JSON)

    requested_by_user: Mapped[UserModel] = relationship(foreign_keys=[requested_by_id])
    approved_by_user: Mapped[UserModel | None] = relationship(foreign_keys=[approved_by_id])
    target_device: Mapped[DeviceModel | None] = relationship()
    operation_requests: Mapped[list[OperationRequestModel]] = relationship(
        back_populates="approval"
    )


class AuditLogModel(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint(
            "risk_level IN ('READ_ONLY', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="audit_risk_level",
        ),
        CheckConstraint(
            "authorization_result IN ('ALLOW', 'DENY')", name="audit_authorization_result"
        ),
        CheckConstraint(
            "execution_status IN ('NOT_EXECUTED', 'PENDING_APPROVAL', "
            "'SUCCEEDED', 'FAILED', 'DENIED')",
            name="audit_execution_status",
        ),
        Index("idx_audit_logs_actor_timestamp", "actor_id", "timestamp"),
        Index("idx_audit_logs_device_timestamp", "device_id", "timestamp"),
        Index("idx_audit_logs_correlation_id", "correlation_id"),
    )

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    actor_role: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    arguments_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    target_resource: Mapped[str | None] = mapped_column(String(240))
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL")
    )
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    authorization_result: Mapped[str] = mapped_column(String(32), nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    approval_status: Mapped[str | None] = mapped_column(String(32))
    execution_status: Mapped[str] = mapped_column(String(32), nullable=False)
    result_summary: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)

    actor: Mapped[UserModel | None] = relationship()
    device: Mapped[DeviceModel | None] = relationship()


class ToolExecutionModel(UuidPkMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "tool_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('REQUESTED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'DENIED')",
            name="tool_execution_status",
        ),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0", name="tool_execution_latency_non_negative"
        ),
        Index("idx_tool_executions_tool_timestamp", "tool_name", "started_at"),
        Index("idx_tool_executions_correlation_id", "correlation_id"),
    )
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(64))
    result_summary: Mapped[str | None] = mapped_column(Text)

    actor: Mapped[UserModel | None] = relationship()


class KnowledgeDocumentModel(UuidPkMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        CheckConstraint(
            "document_type IN ('MANUAL', 'SOP', 'TROUBLESHOOTING', "
            "'CONFIGURATION_GUIDE', 'ENGINEERING_NOTE')",
            name="knowledge_document_type",
        ),
        Index("idx_knowledge_documents_type", "document_type"),
    )
    external_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class OperationRequestModel(UuidPkMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "operation_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('REQUESTED', 'PENDING_APPROVAL', 'APPROVED', "
            "'EXECUTING', 'EXECUTED', 'FAILED', 'DENIED', 'EXPIRED')",
            name="operation_request_status",
        ),
        Index("idx_operation_requests_status_created_at", "status", "created_at"),
        Index("idx_operation_requests_target_device_created_at", "target_device", "created_at"),
    )
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, unique=True)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("approvals.id", ondelete="SET NULL")
    )
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    arguments: Mapped[JsonDict] = mapped_column(JSON, nullable=False, default=dict)
    target_device_id: Mapped[uuid.UUID | None] = mapped_column(
        "target_device", Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    approval: Mapped[ApprovalModel | None] = relationship(back_populates="operation_requests")
    target_device: Mapped[DeviceModel | None] = relationship()


class WorkflowModel(UuidPkMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "workflows"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PLANNED', 'VALIDATED', 'RUNNING', 'WAITING_APPROVAL', "
            "'COMPLETED', 'FAILED', 'CANCELLED')",
            name="workflow_status",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="workflow_confidence_range"),
        Index("idx_workflows_status_created_at", "status", "created_at"),
        Index("idx_workflows_created_by_created_at", "created_by", "created_at"),
    )

    user_request: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    target_environment: Mapped[str] = mapped_column(
        String(64), nullable=False, default="dev", server_default="dev"
    )
    planner_model: Mapped[str] = mapped_column(String(120), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    original_plan: Mapped[JsonDict] = mapped_column(JSON, nullable=False, default=dict)
    policy_transformed_plan: Mapped[JsonDict] = mapped_column(JSON, nullable=False, default=dict)
    audit_events: Mapped[list[JsonDict]] = mapped_column(JSON, nullable=False, default=list)

    nodes: Mapped[list[WorkflowNodeModel]] = relationship(
        back_populates="workflow",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    edges: Mapped[list[WorkflowEdgeModel]] = relationship(
        back_populates="workflow",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class WorkflowNodeModel(UuidPkMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "workflow_nodes"
    __table_args__ = (
        UniqueConstraint("workflow_id", "node_key", name="uq_workflow_nodes_workflow_node_key"),
        CheckConstraint(
            "execution_status IN ('PENDING', 'READY', 'BLOCKED', 'DENIED', "
            "'WAITING_APPROVAL', 'RUNNING', 'SUCCEEDED', 'FAILED', 'RETRYING', "
            "'COMPENSATING', 'COMPENSATED', 'SKIPPED', 'CANCELLED')",
            name="workflow_node_execution_status",
        ),
        Index("idx_workflow_nodes_workflow_status", "workflow_id", "execution_status"),
        Index("idx_workflow_nodes_tool_name", "tool_name"),
    )

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    node_key: Mapped[str] = mapped_column(String(120), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_server: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    arguments: Mapped[JsonDict] = mapped_column(JSON, nullable=False, default=dict)
    argument_references: Mapped[list[JsonDict]] = mapped_column(JSON, nullable=False, default=list)
    depends_on: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    condition: Mapped[str | None] = mapped_column(Text)
    typed_condition: Mapped[JsonDict | None] = mapped_column(JSON)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    execution_status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    retry_strategy: Mapped[str] = mapped_column(
        String(32), nullable=False, default="NO_RETRY", server_default="NO_RETRY"
    )
    timeout_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default="30"
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_reference: Mapped[str | None] = mapped_column(String(240))
    compensation_tool: Mapped[str | None] = mapped_column(String(128))
    policy_evaluation: Mapped[JsonDict | None] = mapped_column(JSON)
    knowledge_references: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    workflow: Mapped[WorkflowModel] = relationship(back_populates="nodes")


class WorkflowEdgeModel(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "workflow_edges"
    __table_args__ = (
        Index("idx_workflow_edges_workflow_source", "workflow_id", "source_node"),
        Index("idx_workflow_edges_workflow_destination", "workflow_id", "destination_node"),
    )

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    source_node: Mapped[str] = mapped_column(String(120), nullable=False)
    destination_node: Mapped[str] = mapped_column(String(120), nullable=False)
    condition: Mapped[str | None] = mapped_column(Text)

    workflow: Mapped[WorkflowModel] = relationship(back_populates="edges")
