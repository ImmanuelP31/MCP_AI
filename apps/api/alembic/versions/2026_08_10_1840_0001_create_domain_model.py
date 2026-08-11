from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0001_create_domain_model"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None
    json_object_default = sa.text("'{}'::jsonb") if is_postgres else sa.text("'{}'")
    json_array_default = sa.text("'[]'::jsonb") if is_postgres else sa.text("'[]'")

    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="ACTIVE", nullable=False),
        *common_columns(uuid_default, versioned=True),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'DISABLED', 'LOCKED')", name="ck_users_user_status"
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_status", "users", ["status"])

    op.create_table(
        "roles",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        *common_columns(uuid_default, versioned=True),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )

    op.create_table(
        "permissions",
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        *common_columns(uuid_default, versioned=True),
        sa.UniqueConstraint("name", name="uq_permissions_name"),
    )

    op.create_table(
        "devices",
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("serial_number", sa.String(length=128), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("site", sa.String(length=200), nullable=False),
        sa.Column("firmware_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("health_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        *common_columns(uuid_default, versioned=True),
        sa.CheckConstraint(
            "status IN ('HEALTHY', 'WARNING', 'CRITICAL', 'OFFLINE')",
            name="ck_devices_device_status",
        ),
        sa.CheckConstraint(
            "health_score >= 0 AND health_score <= 100",
            name="ck_devices_device_health_score_range",
        ),
        sa.UniqueConstraint("device_id", name="uq_devices_device_id"),
        sa.UniqueConstraint("serial_number", name="uq_devices_serial_number"),
    )
    op.create_index("idx_devices_status", "devices", ["status"])
    op.create_index("idx_devices_site_status", "devices", ["site", "status"])

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        *common_columns(uuid_default),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_id", sa.Uuid(), nullable=False),
        *common_columns(uuid_default),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "role_id",
            "permission_id",
            name="uq_role_permissions_role_permission",
        ),
    )

    op.create_table(
        "device_services",
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("service_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("service_version", sa.String(length=64), nullable=False),
        sa.Column("last_restart_at", sa.DateTime(timezone=True), nullable=True),
        *common_columns(uuid_default, versioned=True),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'DEGRADED', 'STOPPED', 'CRASHED')",
            name="ck_device_services_service_status",
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "device_id",
            "service_name",
            name="uq_device_services_device_service",
        ),
    )
    op.create_index(
        "idx_device_services_device_status",
        "device_services",
        ["device_id", "status"],
    )

    op.create_table(
        "telemetry",
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cpu_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("memory_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("network_latency_ms", sa.Numeric(8, 2), nullable=False),
        sa.Column("packet_loss_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("temperature_c", sa.Numeric(5, 2), nullable=False),
        sa.Column("uptime_seconds", sa.Integer(), nullable=False),
        sa.Column("disk_percent", sa.Numeric(5, 2), nullable=False),
        *common_columns(uuid_default),
        sa.CheckConstraint(
            "cpu_percent >= 0 AND cpu_percent <= 100",
            name="ck_telemetry_telemetry_cpu_range",
        ),
        sa.CheckConstraint(
            "memory_percent >= 0 AND memory_percent <= 100",
            name="ck_telemetry_telemetry_memory_range",
        ),
        sa.CheckConstraint(
            "packet_loss_percent >= 0 AND packet_loss_percent <= 100",
            name="ck_telemetry_telemetry_packet_loss_range",
        ),
        sa.CheckConstraint(
            "temperature_c >= -40 AND temperature_c <= 125",
            name="ck_telemetry_telemetry_temperature_range",
        ),
        sa.CheckConstraint(
            "disk_percent >= 0 AND disk_percent <= 100",
            name="ck_telemetry_telemetry_disk_range",
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_telemetry_device_timestamp", "telemetry", ["device_id", "timestamp"])

    op.create_table(
        "alerts",
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.Uuid(), nullable=True),
        *common_columns(uuid_default, versioned=True),
        sa.CheckConstraint(
            "severity IN ('INFO', 'WARNING', 'CRITICAL')",
            name="ck_alerts_alert_severity",
        ),
        sa.ForeignKeyConstraint(["acknowledged_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_alerts_device_timestamp", "alerts", ["device_id", "timestamp"])
    op.create_index("idx_alerts_severity_timestamp", "alerts", ["severity", "timestamp"])

    op.create_table(
        "incidents",
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        *common_columns(uuid_default, versioned=True),
        sa.CheckConstraint(
            "severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_incidents_incident_severity",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'INVESTIGATING', 'MITIGATED', 'RESOLVED')",
            name="ck_incidents_incident_status",
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_incidents_device_created_at", "incidents", ["device_id", "created_at"])
    op.create_index("idx_incidents_status_created_at", "incidents", ["status", "created_at"])

    op.create_table(
        "incident_events",
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), server_default=json_object_default, nullable=False),
        *common_columns(uuid_default),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_incident_events_incident_timestamp",
        "incident_events",
        ["incident_id", "timestamp"],
    )

    op.create_table(
        "diagnostic_runs",
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("evidence", sa.JSON(), server_default=json_object_default, nullable=False),
        *common_columns(uuid_default, versioned=True),
        sa.CheckConstraint(
            "status IN ('REQUESTED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="ck_diagnostic_runs_diagnostic_status",
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "idx_diagnostic_runs_device_started_at",
        "diagnostic_runs",
        ["device_id", "started_at"],
    )

    op.create_table(
        "tickets",
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("assignee", sa.Uuid(), nullable=True),
        sa.Column("team", sa.String(length=128), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("related_incident", sa.Uuid(), nullable=True),
        sa.Column(
            "diagnostic_evidence",
            sa.JSON(),
            server_default=json_object_default,
            nullable=False,
        ),
        *common_columns(uuid_default, versioned=True),
        sa.CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_tickets_ticket_priority",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'IN_PROGRESS', 'BLOCKED', 'RESOLVED', 'CLOSED')",
            name="ck_tickets_ticket_status",
        ),
        sa.ForeignKeyConstraint(["assignee"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["related_incident"], ["incidents.id"], ondelete="SET NULL"),
    )
    op.create_index("idx_tickets_status_priority", "tickets", ["status", "priority"])
    op.create_index("idx_tickets_device_created_at", "tickets", ["device_id", "created_at"])

    op.create_table(
        "approvals",
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("arguments", sa.JSON(), server_default=json_object_default, nullable=False),
        sa.Column("target_device", sa.Uuid(), nullable=True),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_result", sa.JSON(), nullable=True),
        *common_columns(uuid_default, versioned=True),
        sa.CheckConstraint(
            "risk_level IN ('HIGH', 'CRITICAL')", name="ck_approvals_approval_risk_level"
        ),
        sa.CheckConstraint(
            "state IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED', 'EXECUTED', 'FAILED')",
            name="ck_approvals_approval_state",
        ),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["target_device"], ["devices.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("request_id", name="uq_approvals_request_id"),
    )
    op.create_index("idx_approvals_state_expires_at", "approvals", ["state", "expires_at"])
    op.create_index(
        "idx_approvals_requested_by_created_at",
        "approvals",
        ["requested_by", "created_at"],
    )

    op.create_table(
        "audit_logs",
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_role", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("arguments_hash", sa.String(length=128), nullable=False),
        sa.Column("target_resource", sa.String(length=240), nullable=True),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("authorization_result", sa.String(length=32), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("approval_status", sa.String(length=32), nullable=True),
        sa.Column("execution_status", sa.String(length=32), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        *common_columns(uuid_default),
        sa.CheckConstraint(
            "risk_level IN ('READ_ONLY', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_audit_logs_audit_risk_level",
        ),
        sa.CheckConstraint(
            "authorization_result IN ('ALLOW', 'DENY')",
            name="ck_audit_logs_audit_authorization_result",
        ),
        sa.CheckConstraint(
            "execution_status IN ('NOT_EXECUTED', 'PENDING_APPROVAL', "
            "'SUCCEEDED', 'FAILED', 'DENIED')",
            name="ck_audit_logs_audit_execution_status",
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="SET NULL"),
    )
    op.create_index("idx_audit_logs_actor_timestamp", "audit_logs", ["actor_id", "timestamp"])
    op.create_index("idx_audit_logs_device_timestamp", "audit_logs", ["device_id", "timestamp"])
    op.create_index("idx_audit_logs_correlation_id", "audit_logs", ["correlation_id"])

    op.create_table(
        "tool_executions",
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        *common_columns(uuid_default, versioned=True),
        sa.CheckConstraint(
            "status IN ('REQUESTED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'DENIED')",
            name="ck_tool_executions_tool_execution_status",
        ),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_tool_executions_tool_execution_latency_non_negative",
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "idx_tool_executions_tool_timestamp",
        "tool_executions",
        ["tool_name", "started_at"],
    )
    op.create_index("idx_tool_executions_correlation_id", "tool_executions", ["correlation_id"])

    op.create_table(
        "knowledge_documents",
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("document_type", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), server_default=json_array_default, nullable=False),
        *common_columns(uuid_default, versioned=True),
        sa.CheckConstraint(
            "document_type IN ('MANUAL', 'SOP', 'TROUBLESHOOTING', "
            "'CONFIGURATION_GUIDE', 'ENGINEERING_NOTE')",
            name="ck_knowledge_documents_knowledge_document_type",
        ),
        sa.UniqueConstraint("external_id", name="uq_knowledge_documents_external_id"),
    )
    op.create_index("idx_knowledge_documents_type", "knowledge_documents", ["document_type"])

    op.create_table(
        "operation_requests",
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("arguments", sa.JSON(), server_default=json_object_default, nullable=False),
        sa.Column("target_device", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        *common_columns(uuid_default, versioned=True),
        sa.CheckConstraint(
            "status IN ('REQUESTED', 'PENDING_APPROVAL', 'APPROVED', 'EXECUTING', "
            "'EXECUTED', 'FAILED', 'DENIED', 'EXPIRED')",
            name="ck_operation_requests_operation_request_status",
        ),
        sa.ForeignKeyConstraint(["approval_id"], ["approvals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_device"], ["devices.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("idempotency_key", name="uq_operation_requests_idempotency_key"),
        sa.UniqueConstraint("request_id", name="uq_operation_requests_request_id"),
    )
    op.create_index(
        "idx_operation_requests_status_created_at",
        "operation_requests",
        ["status", "created_at"],
    )
    op.create_index(
        "idx_operation_requests_target_device_created_at",
        "operation_requests",
        ["target_device", "created_at"],
    )


def downgrade() -> None:
    for table_name in (
        "operation_requests",
        "knowledge_documents",
        "tool_executions",
        "audit_logs",
        "approvals",
        "tickets",
        "diagnostic_runs",
        "incident_events",
        "incidents",
        "alerts",
        "telemetry",
        "device_services",
        "role_permissions",
        "user_roles",
        "devices",
        "permissions",
        "roles",
        "users",
    ):
        op.drop_table(table_name)


def common_columns(
    uuid_default: sa.TextClause | None,
    *,
    versioned: bool = False,
) -> list[sa.schema.SchemaItem]:
    columns: list[sa.schema.SchemaItem] = [
        sa.Column("id", sa.Uuid(), server_default=uuid_default, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    ]
    if versioned:
        columns.insert(1, sa.Column("version", sa.Integer(), server_default="1", nullable=False))
    return columns
