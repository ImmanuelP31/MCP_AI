from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from mcp_ops_ai_agent.gateway import GatewayClient
from mcp_ops_ai_agent.workflows.events import (
    InMemoryWorkflowEventPublisher,
    WorkflowOutboxPublisher,
)
from mcp_ops_ai_agent.workflows.models import (
    Workflow,
    WorkflowApprovalState,
    WorkflowNode,
    WorkflowNodeStatus,
    WorkflowPlanRequest,
    WorkflowStatus,
)
from mcp_ops_ai_agent.workflows.service import WorkflowPlanningService
from mcp_ops_api.db.models import WorkflowEventOutboxModel
from mcp_ops_api.db.repositories import WorkflowRepository
from mcp_ops_mcp_gateway.models import GatewayDecision, GatewayToolRequest, GatewayToolResponse
from sqlalchemy import create_engine, select
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


def test_workflow_node_approval_state_is_persisted() -> None:
    database_url = f"sqlite:///{isolated_database_path('workflow_approval_state.db')}"
    command.upgrade(_alembic_config(database_url), "head")
    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    approval_id = uuid4()
    base = _workflow()
    workflow = base.model_copy(
        update={
            "status": WorkflowStatus.WAITING_APPROVAL,
            "nodes": [
                base.nodes[0].model_copy(
                    update={
                        "execution_status": WorkflowNodeStatus.WAITING_APPROVAL,
                        "approval_id": approval_id,
                        "approval_state": WorkflowApprovalState.WAITING_APPROVAL,
                    }
                )
            ],
        },
        deep=True,
    )

    with session_factory() as session:
        WorkflowRepository(session).save_workflow(workflow)
        session.commit()

    with session_factory() as session:
        loaded = WorkflowRepository(session).get_workflow(workflow.id)

    assert loaded is not None
    assert loaded.nodes[0].approval_id == approval_id
    assert loaded.nodes[0].approval_state == WorkflowApprovalState.WAITING_APPROVAL


def test_workflow_checkpoint_and_outbox_commit_atomically() -> None:
    database_url = f"sqlite:///{isolated_database_path('workflow_outbox.db')}"
    command.upgrade(_alembic_config(database_url), "head")
    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    workflow = _workflow()

    with session_factory() as session:
        repository = WorkflowRepository(session)
        repository.save_workflow(workflow)
        session.commit()

    with session_factory() as session:
        service = WorkflowPlanningService(
            repository=WorkflowRepository(session),
            gateway_client=StaticGateway(),
        )
        executed = service.execute(workflow.id, role="ENGINEER")
        session.commit()

    with session_factory() as session:
        repository = WorkflowRepository(session)
        pending = repository.pending_workflow_events(limit=20)
        publisher = InMemoryWorkflowEventPublisher()
        published = WorkflowOutboxPublisher(repository=repository, publisher=publisher).drain(
            limit=20
        )
        session.commit()

    with session_factory() as session:
        statuses = session.scalars(select(WorkflowEventOutboxModel.status)).all()

    assert executed.status == WorkflowStatus.COMPLETED
    assert pending
    assert published == len(pending)
    assert {event.event_id for event in publisher.events} == {event.event_id for event in pending}
    assert set(statuses) == {"PUBLISHED"}


def test_workflow_outbox_rolls_back_with_checkpoint_state() -> None:
    database_url = f"sqlite:///{isolated_database_path('workflow_outbox_rollback.db')}"
    command.upgrade(_alembic_config(database_url), "head")
    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    workflow = _workflow()

    with session_factory() as session:
        WorkflowRepository(session).save_workflow(workflow)
        session.commit()

    with session_factory() as session:
        service = WorkflowPlanningService(
            repository=WorkflowRepository(session),
            gateway_client=StaticGateway(),
        )
        service.execute(workflow.id, role="ENGINEER")
        session.rollback()

    with session_factory() as session:
        repository = WorkflowRepository(session)
        loaded = repository.get_workflow(workflow.id)
        pending = repository.pending_workflow_events(limit=20)

    assert loaded is not None
    assert loaded.status == WorkflowStatus.VALIDATED
    assert pending == []


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
        user_request="Run tests.",
        status=WorkflowStatus.VALIDATED,
        created_by="engineer",
        planner_model="test",
        confidence=0.9,
        nodes=[
            WorkflowNode(
                id="tests",
                tool_name="run_tests",
                tool_server="cicd-mcp",
                description="Run unit tests.",
                arguments={
                    "repository": "ImmanuelP31/MCP_AI",
                    "test_suite": "unit",
                },
                risk_level="MEDIUM",
            )
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


def _alembic_config(database_url: str) -> Config:
    config = Config(str(ROOT / "apps" / "api" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "apps" / "api" / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config
