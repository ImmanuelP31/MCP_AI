from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from mcp_ops_ai_agent.gateway import GatewayClient
from mcp_ops_ai_agent.workflows.models import (
    RetryStrategy,
    Workflow,
    WorkflowNode,
    WorkflowNodeStatus,
    WorkflowStatus,
)
from mcp_ops_ai_agent.workflows.service import WorkflowPlanningService
from mcp_ops_api.db.repositories import WorkflowRepository
from mcp_ops_mcp_gateway.models import GatewayDecision, GatewayToolRequest, GatewayToolResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests.conftest import isolated_database_path

ROOT = Path(__file__).resolve().parents[2]


def test_partially_completed_workflow_recovers_after_backend_restart() -> None:
    database_url = f"sqlite:///{isolated_database_path('workflow-resume.db')}"
    command.upgrade(_alembic_config(database_url), "head")
    store = SqlAlchemyWorkflowStore(database_url)
    workflow = _workflow()
    store.save_workflow(workflow)

    restarted_service = WorkflowPlanningService(
        repository=store,
        gateway_client=StaticGateway(),
    )
    recovered = restarted_service.retry_node(workflow.id, "ticket", role="ENGINEER")

    nodes = {node.id: node for node in recovered.nodes}
    assert recovered.status == WorkflowStatus.COMPLETED
    assert nodes["commit"].execution_status == WorkflowNodeStatus.SUCCEEDED
    assert nodes["commit"].attempts == 1
    assert nodes["ticket"].execution_status == WorkflowNodeStatus.SUCCEEDED
    assert nodes["ticket"].attempts == 2


class SqlAlchemyWorkflowStore:
    def __init__(self, database_url: str) -> None:
        self.session_factory = sessionmaker(bind=create_engine(database_url))

    def save_workflow(self, workflow: Workflow) -> Workflow:
        with self.session_factory() as session:
            saved = WorkflowRepository(session).save_workflow(workflow)
            session.commit()
            return saved

    def get_workflow(self, workflow_id: UUID) -> Workflow | None:
        with self.session_factory() as session:
            return WorkflowRepository(session).get_workflow(workflow_id)


class StaticGateway(GatewayClient):
    def call_tool(self, request: GatewayToolRequest) -> GatewayToolResponse:
        return GatewayToolResponse(
            ok=True,
            decision=GatewayDecision.ALLOWED,
            correlation_id=uuid4(),
            data={"tool_result": {"ok": True}},
        )


def _workflow() -> Workflow:
    workflow = Workflow(
        user_request="Recover partial workflow.",
        status=WorkflowStatus.FAILED,
        created_by="engineer",
        planner_model="test",
        confidence=0.9,
        nodes=[
            _node("commit").model_copy(
                update={
                    "execution_status": WorkflowNodeStatus.SUCCEEDED,
                    "attempts": 1,
                }
            ),
            _node("ticket", depends_on=["commit"]).model_copy(
                update={
                    "execution_status": WorkflowNodeStatus.FAILED,
                    "attempts": 1,
                    "last_error": "transient gateway failure",
                }
            ),
        ],
    )
    return workflow.model_copy(
        update={
            "nodes": [
                node.model_copy(update={"workflow_id": workflow.id})
                for node in workflow.nodes
            ]
        }
    )


def _node(node_id: str, *, depends_on: list[str] | None = None) -> WorkflowNode:
    return WorkflowNode(
        id=node_id,
        tool_name="create_ticket",
        tool_server="ticket-mcp",
        description="Create engineering ticket.",
        arguments={
            "device_id": "SIM-014",
            "title": "Workflow ticket",
            "description": "Persistent resume test",
            "priority": "HIGH",
            "team": "Engineering Operations",
            "diagnostic_evidence": {"source": "test"},
        },
        depends_on=depends_on or [],
        risk_level="MEDIUM",
        max_retries=1,
        retry_strategy=RetryStrategy.FIXED_DELAY,
    )


def _alembic_config(database_url: str) -> Config:
    config = Config(str(ROOT / "apps" / "api" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "apps" / "api" / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config
