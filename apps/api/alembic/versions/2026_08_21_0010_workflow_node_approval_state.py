from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0010_workflow_node_approval_state"
down_revision = "0009_workflow_event_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPROVAL_STATES = (
    "'NOT_REQUIRED', 'WAITING_APPROVAL', 'APPROVED', 'EXECUTION_QUEUED', "
    "'EXECUTING', 'SUCCEEDED', 'REJECTED', 'EXPIRED', 'FAILED'"
)


def upgrade() -> None:
    with op.batch_alter_table("workflow_nodes") as batch_op:
        batch_op.add_column(sa.Column("approval_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "approval_state",
                sa.String(length=32),
                server_default="NOT_REQUIRED",
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            "workflow_node_approval_state",
            f"approval_state IN ({APPROVAL_STATES})",
        )
    op.create_index(
        "idx_workflow_nodes_approval_id",
        "workflow_nodes",
        ["approval_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_workflow_nodes_approval_id", table_name="workflow_nodes")
    with op.batch_alter_table("workflow_nodes") as batch_op:
        batch_op.drop_constraint("workflow_node_approval_state", type_="check")
        batch_op.drop_column("approval_state")
        batch_op.drop_column("approval_id")
