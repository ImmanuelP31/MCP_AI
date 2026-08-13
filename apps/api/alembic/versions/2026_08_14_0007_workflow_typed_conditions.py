from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0007_workflow_typed_conditions"
down_revision = "0006_workflow_argument_references"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_nodes", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("typed_condition", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workflow_nodes", recreate="always") as batch_op:
        batch_op.drop_column("typed_condition")
