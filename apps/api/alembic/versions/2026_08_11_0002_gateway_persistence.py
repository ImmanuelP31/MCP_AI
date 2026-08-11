from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0002_gateway_persistence"
down_revision = "0001_create_domain_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_default = sa.text("'{}'::jsonb") if op.get_bind().dialect.name == "postgresql" else None

    op.create_table(
        "gateway_approvals",
        sa.Column("approval_id", sa.Uuid(), nullable=False),
        sa.Column("requester_id", sa.String(length=160), nullable=False),
        sa.Column("requester_type", sa.String(length=32), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("arguments", sa.JSON(), server_default=json_default, nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by", sa.String(length=160), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by", sa.String(length=160), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(length=500), nullable=True),
        sa.Column("execution_result", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED','EXPIRED','EXECUTED','FAILED')",
            name="ck_gateway_approvals_status",
        ),
        sa.PrimaryKeyConstraint("approval_id"),
    )
    op.create_index("ix_gateway_approvals_requester_id", "gateway_approvals", ["requester_id"])
    op.create_index("ix_gateway_approvals_tool_name", "gateway_approvals", ["tool_name"])
    op.create_index("ix_gateway_approvals_status", "gateway_approvals", ["status"])
    op.create_index("ix_gateway_approvals_expires_at", "gateway_approvals", ["expires_at"])

    op.create_table(
        "gateway_approval_events",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_gateway_approval_events_approval_id",
        "gateway_approval_events",
        ["approval_id"],
    )

    op.create_table(
        "gateway_audit_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.String(length=160), nullable=False),
        sa.Column("actor_role", sa.String(length=64), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("authorization_result", sa.String(length=32), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=True),
        sa.Column("approval_status", sa.String(length=32), nullable=True),
        sa.Column("execution_status", sa.String(length=64), nullable=False),
        sa.Column("result_summary", sa.String(length=500), nullable=False),
        sa.Column("argument_hash", sa.String(length=128), nullable=True),
        sa.Column("target_resource", sa.String(length=240), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gateway_audit_records_actor_id", "gateway_audit_records", ["actor_id"])
    op.create_index("ix_gateway_audit_records_tool_name", "gateway_audit_records", ["tool_name"])
    op.create_index(
        "ix_gateway_audit_records_correlation_id",
        "gateway_audit_records",
        ["correlation_id"],
    )
    op.create_index(
        "ix_gateway_audit_records_target_resource",
        "gateway_audit_records",
        ["target_resource"],
    )

    op.create_table(
        "gateway_idempotency_keys",
        sa.Column("principal_id", sa.String(length=160), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("principal_id", "idempotency_key"),
    )

    op.create_table(
        "gateway_rate_limit_calls",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("principal_id", sa.String(length=160), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("called_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_gateway_rate_limit_calls_principal_id",
        "gateway_rate_limit_calls",
        ["principal_id"],
    )
    op.create_index(
        "ix_gateway_rate_limit_calls_tool_name",
        "gateway_rate_limit_calls",
        ["tool_name"],
    )
    op.create_index(
        "ix_gateway_rate_limit_calls_called_at",
        "gateway_rate_limit_calls",
        ["called_at"],
    )


def downgrade() -> None:
    op.drop_table("gateway_rate_limit_calls")
    op.drop_table("gateway_idempotency_keys")
    op.drop_table("gateway_audit_records")
    op.drop_table("gateway_approval_events")
    op.drop_table("gateway_approvals")
