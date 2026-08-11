from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0004_workflow_resiliency"
down_revision = "0003_workflow_dag"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_nodes", recreate="always") as batch_op:
        batch_op.drop_constraint(
            "ck_workflow_nodes_workflow_node_execution_status",
            type_="check",
        )
        batch_op.add_column(sa.Column("attempts", sa.Integer(), server_default="0", nullable=False))
        batch_op.add_column(
            sa.Column("max_retries", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(
            sa.Column(
                "retry_strategy",
                sa.String(length=32),
                server_default="NO_RETRY",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("timeout_seconds", sa.Integer(), server_default="30", nullable=False)
        )
        batch_op.add_column(sa.Column("last_error", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("compensation_tool", sa.String(length=128), nullable=True))
        batch_op.create_check_constraint(
            "workflow_node_execution_status",
            "execution_status IN ('PENDING', 'READY', 'BLOCKED', 'DENIED', "
            "'WAITING_APPROVAL', 'RUNNING', 'SUCCEEDED', 'FAILED', 'RETRYING', "
            "'COMPENSATING', 'COMPENSATED', 'SKIPPED', 'CANCELLED')",
        )


def downgrade() -> None:
    with op.batch_alter_table("workflow_nodes", recreate="always") as batch_op:
        batch_op.drop_constraint(
            "ck_workflow_nodes_workflow_node_execution_status",
            type_="check",
        )
        batch_op.drop_column("compensation_tool")
        batch_op.drop_column("next_retry_at")
        batch_op.drop_column("last_attempt_at")
        batch_op.drop_column("completed_at")
        batch_op.drop_column("started_at")
        batch_op.drop_column("last_error")
        batch_op.drop_column("timeout_seconds")
        batch_op.drop_column("retry_strategy")
        batch_op.drop_column("max_retries")
        batch_op.drop_column("attempts")
        batch_op.create_check_constraint(
            "workflow_node_execution_status",
            "execution_status IN ('PENDING', 'BLOCKED', 'DENIED', 'WAITING_APPROVAL', "
            "'RUNNING', 'SUCCEEDED', 'FAILED', 'SKIPPED', 'CANCELLED')",
        )
