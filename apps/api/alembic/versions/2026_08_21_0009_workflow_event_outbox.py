from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0009_workflow_event_outbox"
down_revision = "0008_gateway_idempotency_outcomes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_event_outbox",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=160), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="PENDING", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_workflow_event_outbox_event_id"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PUBLISHED', 'FAILED')",
            name="workflow_event_outbox_status",
        ),
    )
    op.create_index(
        "idx_workflow_event_outbox_status_created_at",
        "workflow_event_outbox",
        ["status", "created_at"],
    )
    op.create_index(
        "idx_workflow_event_outbox_aggregate_created_at",
        "workflow_event_outbox",
        ["aggregate_id", "created_at"],
    )
    op.create_index(
        "idx_workflow_event_outbox_event_type",
        "workflow_event_outbox",
        ["event_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_workflow_event_outbox_event_type", table_name="workflow_event_outbox")
    op.drop_index(
        "idx_workflow_event_outbox_aggregate_created_at",
        table_name="workflow_event_outbox",
    )
    op.drop_index("idx_workflow_event_outbox_status_created_at", table_name="workflow_event_outbox")
    op.drop_table("workflow_event_outbox")
