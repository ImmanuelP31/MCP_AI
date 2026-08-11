from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from mcp_ops_ai_agent.workflows.models import WorkflowPlanRequest
from mcp_ops_ai_agent.workflows.service import WorkflowPlanningService
from mcp_ops_api.db.repositories import WorkflowRepository
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests.conftest import isolated_database_path

ROOT = Path(__file__).resolve().parents[2]


def test_workflow_plan_is_persisted_and_loaded_from_database() -> None:
    database_url = f"sqlite:///{isolated_database_path('workflows.db')}"
    command.upgrade(_alembic_config(database_url), "head")
    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        service = WorkflowPlanningService(repository=WorkflowRepository(session))
        result = service.plan(
            WorkflowPlanRequest(
                user_request="Create a maintenance ticket for SIM-014.",
                role="ENGINEER",
                created_by="engineer",
                top_k=20,
            )
        )
        session.commit()
        workflow_id = result.workflow.id

    with session_factory() as session:
        loaded = WorkflowRepository(session).get_workflow(workflow_id)

    assert loaded is not None
    assert loaded.id == workflow_id
    assert loaded.status == "VALIDATED"
    assert "create_ticket" in {node.tool_name for node in loaded.nodes}
    assert loaded.edges


def test_workflow_knowledge_references_are_persisted() -> None:
    database_url = f"sqlite:///{isolated_database_path('workflow_rag.db')}"
    command.upgrade(_alembic_config(database_url), "head")
    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        service = WorkflowPlanningService(repository=WorkflowRepository(session))
        result = service.plan(
            WorkflowPlanRequest(
                user_request="Deploy payments-api to staging.",
                role="OPERATOR",
                created_by="operator",
                target_environment="staging",
                top_k=20,
            )
        )
        session.commit()
        workflow_id = result.workflow.id

    with session_factory() as session:
        loaded = WorkflowRepository(session).get_workflow(workflow_id)

    assert loaded is not None
    assert loaded.original_plan["retrieved_knowledge"]
    assert any(node.knowledge_references for node in loaded.nodes)


def _alembic_config(database_url: str) -> Config:
    config = Config(str(ROOT / "apps" / "api" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "apps" / "api" / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config
