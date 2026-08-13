from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0006_workflow_argument_references"
down_revision = "0005_workflow_knowledge_references"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_nodes", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column("argument_references", sa.JSON(), server_default="[]", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("workflow_nodes", recreate="always") as batch_op:
        batch_op.drop_column("argument_references")
