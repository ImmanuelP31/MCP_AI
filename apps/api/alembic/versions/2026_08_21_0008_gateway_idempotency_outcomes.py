from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0008_gateway_idempotency_outcomes"
down_revision = "0007_workflow_typed_conditions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("gateway_idempotency_keys") as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(length=32),
                server_default="RESERVED",
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("response_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("gateway_idempotency_keys") as batch_op:
        batch_op.drop_column("response_json")
        batch_op.drop_column("status")
