from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from typing import TypeVar

from mcp_ops_ai_agent.workflows.models import (
    RetryStrategy,
    Workflow,
    WorkflowAuditEvent,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeStatus,
    WorkflowPolicyEvaluation,
    WorkflowStatus,
)
from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session, selectinload

from mcp_ops_api.db.models import (
    ApprovalModel,
    AuditLogModel,
    DeviceModel,
    IncidentModel,
    KnowledgeDocumentModel,
    TelemetryModel,
    TicketModel,
    ToolExecutionModel,
    WorkflowEdgeModel,
    WorkflowModel,
    WorkflowNodeModel,
)

ModelT = TypeVar("ModelT")
MAX_PAGE_LIMIT = 500


class Repository[ModelT]:
    def __init__(self, session: Session, model_type: type[ModelT]) -> None:
        self.session = session
        self.model_type = model_type

    def add(self, model: ModelT) -> ModelT:
        self.session.add(model)
        return model

    def get(self, model_id: uuid.UUID) -> ModelT | None:
        return self.session.get(self.model_type, model_id)

    def list(self, *, limit: int = 100, offset: int = 0) -> Sequence[ModelT]:
        statement = select(self.model_type).limit(_limit(limit)).offset(_offset(offset))
        return self.session.scalars(statement).all()

    def count(self) -> int:
        statement = select(func.count()).select_from(self.model_type)
        return self.session.scalar(statement) or 0


class DeviceRepository(Repository[DeviceModel]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, DeviceModel)

    def get_by_device_id(self, device_id: str) -> DeviceModel | None:
        statement = (
            select(DeviceModel)
            .where(DeviceModel.device_id == device_id)
            .options(selectinload(DeviceModel.services), selectinload(DeviceModel.incidents))
        )
        return self.session.scalar(statement)

    def list_by_status(self, status: str, *, limit: int = 100) -> Sequence[DeviceModel]:
        statement = (
            select(DeviceModel)
            .where(DeviceModel.status == status)
            .order_by(DeviceModel.device_id)
            .limit(_limit(limit))
        )
        return self.session.scalars(statement).all()

    def latest_telemetry(self, device: DeviceModel, *, limit: int = 10) -> Sequence[TelemetryModel]:
        statement = (
            select(TelemetryModel)
            .where(TelemetryModel.device_id == device.id)
            .order_by(TelemetryModel.timestamp.desc())
            .limit(_limit(limit))
        )
        return self.session.scalars(statement).all()


class IncidentRepository(Repository[IncidentModel]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, IncidentModel)

    def open_for_device(self, device_id: uuid.UUID) -> Sequence[IncidentModel]:
        statement = (
            select(IncidentModel)
            .where(IncidentModel.device_id == device_id)
            .where(IncidentModel.status.in_(["OPEN", "INVESTIGATING"]))
            .order_by(IncidentModel.created_at.desc())
        )
        return self.session.scalars(statement).all()


class TicketRepository(Repository[TicketModel]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, TicketModel)

    def open_tickets(self, *, limit: int = 100) -> Sequence[TicketModel]:
        statement = (
            select(TicketModel)
            .where(TicketModel.status.in_(["OPEN", "IN_PROGRESS", "BLOCKED"]))
            .order_by(TicketModel.created_at.desc())
            .limit(_limit(limit))
        )
        return self.session.scalars(statement).all()

    def for_device(self, device_id: uuid.UUID) -> Sequence[TicketModel]:
        statement = (
            select(TicketModel)
            .where(TicketModel.device_id == device_id)
            .order_by(TicketModel.created_at.desc())
        )
        return self.session.scalars(statement).all()


class ApprovalRepository(Repository[ApprovalModel]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ApprovalModel)

    def pending(self) -> Sequence[ApprovalModel]:
        statement = (
            select(ApprovalModel)
            .where(ApprovalModel.state == "PENDING")
            .order_by(ApprovalModel.expires_at)
        )
        return self.session.scalars(statement).all()

    def get_by_request_id(self, request_id: uuid.UUID) -> ApprovalModel | None:
        return self.session.scalar(
            select(ApprovalModel).where(ApprovalModel.request_id == request_id)
        )


class AuditRepository(Repository[AuditLogModel]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AuditLogModel)

    def for_actor(self, actor_id: uuid.UUID, *, limit: int = 100) -> Sequence[AuditLogModel]:
        return self._ordered_audit_query(
            select(AuditLogModel).where(AuditLogModel.actor_id == actor_id),
            limit=limit,
        )

    def for_device(self, device_id: uuid.UUID, *, limit: int = 100) -> Sequence[AuditLogModel]:
        return self._ordered_audit_query(
            select(AuditLogModel).where(AuditLogModel.device_id == device_id),
            limit=limit,
        )

    def _ordered_audit_query(
        self, statement: Select[tuple[AuditLogModel]], *, limit: int
    ) -> Sequence[AuditLogModel]:
        return self.session.scalars(
            statement.order_by(AuditLogModel.timestamp.desc()).limit(_limit(limit))
        ).all()


class ToolExecutionRepository(Repository[ToolExecutionModel]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ToolExecutionModel)

    def for_tool(self, tool_name: str, *, limit: int = 100) -> Sequence[ToolExecutionModel]:
        statement = (
            select(ToolExecutionModel)
            .where(ToolExecutionModel.tool_name == tool_name)
            .order_by(ToolExecutionModel.started_at.desc())
            .limit(_limit(limit))
        )
        return self.session.scalars(statement).all()


class KnowledgeRepository(Repository[KnowledgeDocumentModel]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, KnowledgeDocumentModel)

    def search_by_tag(self, tag: str) -> Sequence[KnowledgeDocumentModel]:
        documents = self.session.scalars(select(KnowledgeDocumentModel)).all()
        return [document for document in documents if tag in document.tags]


class WorkflowRepository(Repository[WorkflowModel]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, WorkflowModel)

    def save_workflow(self, workflow: Workflow) -> Workflow:
        model = WorkflowModel(
            id=workflow.id,
            version=workflow.version,
            user_request=workflow.user_request,
            status=workflow.status.value,
            created_by=workflow.created_by,
            created_at=workflow.created_at,
            updated_at=workflow.created_at,
            target_environment=workflow.target_environment,
            planner_model=workflow.planner_model,
            confidence=workflow.confidence,
            original_plan=workflow.original_plan,
            policy_transformed_plan=workflow.policy_transformed_plan,
            audit_events=[event.model_dump(mode="json") for event in workflow.audit_events],
        )
        model.nodes = [
            WorkflowNodeModel(
                workflow_id=workflow.id,
                node_key=node.id,
                tool_name=node.tool_name,
                tool_server=node.tool_server,
                description=node.description,
                arguments=node.arguments,
                depends_on=node.depends_on,
                condition=node.condition,
                risk_level=node.risk_level,
                approval_required=node.approval_required,
                execution_status=node.execution_status.value,
                attempts=node.attempts,
                max_retries=node.max_retries,
                retry_strategy=node.retry_strategy.value,
                timeout_seconds=node.timeout_seconds,
                last_error=node.last_error,
                started_at=node.started_at,
                completed_at=node.completed_at,
                last_attempt_at=node.last_attempt_at,
                next_retry_at=node.next_retry_at,
                result_reference=node.result_reference,
                compensation_tool=node.compensation_tool,
                policy_evaluation=node.policy_evaluation.model_dump(mode="json")
                if node.policy_evaluation
                else None,
                knowledge_references=node.knowledge_references,
            )
            for node in workflow.nodes
        ]
        model.edges = [
            WorkflowEdgeModel(
                workflow_id=workflow.id,
                source_node=edge.source,
                destination_node=edge.destination,
                condition=edge.condition,
            )
            for edge in workflow.edges
        ]
        existing = self.session.get(WorkflowModel, workflow.id)
        if existing is not None:
            self.session.execute(
                delete(WorkflowNodeModel).where(WorkflowNodeModel.workflow_id == workflow.id)
            )
            self.session.execute(
                delete(WorkflowEdgeModel).where(WorkflowEdgeModel.workflow_id == workflow.id)
            )
            self.session.delete(existing)
            self.session.flush()
        self.session.add(model)
        self.session.flush()
        return workflow

    def get_workflow(self, workflow_id: uuid.UUID) -> Workflow | None:
        statement = (
            select(WorkflowModel)
            .where(WorkflowModel.id == workflow_id)
            .options(selectinload(WorkflowModel.nodes), selectinload(WorkflowModel.edges))
        )
        model = self.session.scalar(statement)
        if model is None:
            return None
        return _workflow_from_model(model)

    def list_workflows(self, *, limit: int = 100) -> Sequence[Workflow]:
        statement = (
            select(WorkflowModel)
            .options(selectinload(WorkflowModel.nodes), selectinload(WorkflowModel.edges))
            .order_by(WorkflowModel.created_at.desc())
            .limit(_limit(limit))
        )
        return [_workflow_from_model(model) for model in self.session.scalars(statement).all()]


def _limit(value: int) -> int:
    return min(max(value, 1), MAX_PAGE_LIMIT)


def _offset(value: int) -> int:
    return max(value, 0)


def _workflow_from_model(model: WorkflowModel) -> Workflow:
    return Workflow(
        id=model.id,
        user_request=model.user_request,
        status=WorkflowStatus(model.status),
        created_by=model.created_by,
        created_at=model.created_at,
        target_environment=model.target_environment,
        planner_model=model.planner_model,
        confidence=float(model.confidence),
        version=model.version,
        nodes=[
            WorkflowNode(
                id=node.node_key,
                workflow_id=model.id,
                tool_name=node.tool_name,
                tool_server=node.tool_server,
                description=node.description,
                arguments=node.arguments,
                depends_on=node.depends_on,
                condition=node.condition,
                risk_level=node.risk_level,
                approval_required=node.approval_required,
                execution_status=WorkflowNodeStatus(node.execution_status),
                attempts=node.attempts,
                max_retries=node.max_retries,
                retry_strategy=RetryStrategy(node.retry_strategy),
                timeout_seconds=node.timeout_seconds,
                last_error=node.last_error,
                started_at=node.started_at,
                completed_at=node.completed_at,
                last_attempt_at=node.last_attempt_at,
                next_retry_at=node.next_retry_at,
                result_reference=node.result_reference,
                compensation_tool=node.compensation_tool,
                policy_evaluation=WorkflowPolicyEvaluation.model_validate_json(
                    json.dumps(node.policy_evaluation)
                )
                if node.policy_evaluation
                else None,
                knowledge_references=node.knowledge_references,
            )
            for node in sorted(model.nodes, key=lambda item: item.node_key)
        ],
        edges=[
            WorkflowEdge(
                source=edge.source_node,
                destination=edge.destination_node,
                condition=edge.condition,
            )
            for edge in sorted(
                model.edges,
                key=lambda item: (item.source_node, item.destination_node),
            )
        ],
        original_plan=model.original_plan,
        policy_transformed_plan=model.policy_transformed_plan,
        audit_events=[
            WorkflowAuditEvent.model_validate_json(json.dumps(event))
            for event in model.audit_events
        ],
    )
