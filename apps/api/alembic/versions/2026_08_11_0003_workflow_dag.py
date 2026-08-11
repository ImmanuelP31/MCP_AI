from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0003_workflow_dag"
down_revision = "0002_gateway_persistence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    uuid_default = sa.text("gen_random_uuid()") if bind.dialect.name == "postgresql" else None
    json_object_default = sa.text("'{}'::jsonb") if bind.dialect.name == "postgresql" else None
    json_array_default = sa.text("'[]'::jsonb") if bind.dialect.name == "postgresql" else None

    op.create_table(
        "workflows",
        sa.Column("user_request", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("target_environment", sa.String(length=64), server_default="dev", nullable=False),
        sa.Column("planner_model", sa.String(length=120), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("original_plan", sa.JSON(), server_default=json_object_default, nullable=False),
        sa.Column(
            "policy_transformed_plan",
            sa.JSON(),
            server_default=json_object_default,
            nullable=False,
        ),
        sa.Column("audit_events", sa.JSON(), server_default=json_array_default, nullable=False),
        *common_columns(uuid_default, versioned=True),
        sa.CheckConstraint(
            "status IN ('PLANNED', 'VALIDATED', 'RUNNING', 'WAITING_APPROVAL', "
            "'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ck_workflows_workflow_status",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_workflows_workflow_confidence_range",
        ),
    )
    op.create_index("idx_workflows_status_created_at", "workflows", ["status", "created_at"])
    op.create_index(
        "idx_workflows_created_by_created_at",
        "workflows",
        ["created_by", "created_at"],
    )

    op.create_table(
        "workflow_nodes",
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("node_key", sa.String(length=120), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("tool_server", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("arguments", sa.JSON(), server_default=json_object_default, nullable=False),
        sa.Column("depends_on", sa.JSON(), server_default=json_array_default, nullable=False),
        sa.Column("condition", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("execution_status", sa.String(length=32), nullable=False),
        sa.Column("result_reference", sa.String(length=240), nullable=True),
        sa.Column("policy_evaluation", sa.JSON(), nullable=True),
        *common_columns(uuid_default, versioned=True),
        sa.CheckConstraint(
            "execution_status IN ('PENDING', 'BLOCKED', 'DENIED', 'WAITING_APPROVAL', "
            "'RUNNING', 'SUCCEEDED', 'FAILED', 'SKIPPED', 'CANCELLED')",
            name="ck_workflow_nodes_workflow_node_execution_status",
        ),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "workflow_id",
            "node_key",
            name="uq_workflow_nodes_workflow_node_key",
        ),
    )
    op.create_index(
        "idx_workflow_nodes_workflow_status",
        "workflow_nodes",
        ["workflow_id", "execution_status"],
    )
    op.create_index("idx_workflow_nodes_tool_name", "workflow_nodes", ["tool_name"])

    op.create_table(
        "workflow_edges",
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("source_node", sa.String(length=120), nullable=False),
        sa.Column("destination_node", sa.String(length=120), nullable=False),
        sa.Column("condition", sa.Text(), nullable=True),
        *common_columns(uuid_default),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_workflow_edges_workflow_source",
        "workflow_edges",
        ["workflow_id", "source_node"],
    )
    op.create_index(
        "idx_workflow_edges_workflow_destination",
        "workflow_edges",
        ["workflow_id", "destination_node"],
    )


def downgrade() -> None:
    op.drop_table("workflow_edges")
    op.drop_table("workflow_nodes")
    op.drop_table("workflows")


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
