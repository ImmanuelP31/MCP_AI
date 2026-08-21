from __future__ import annotations

from threading import Lock
from typing import Protocol
from uuid import UUID

from mcp_ops_ai_agent.workflows.events import WorkflowOutboxEvent
from mcp_ops_ai_agent.workflows.models import Workflow


class WorkflowRepositoryProtocol(Protocol):
    def save_workflow(self, workflow: Workflow) -> Workflow:
        """Persist workflow state."""

    def save_workflow_with_event(
        self,
        workflow: Workflow,
        event: WorkflowOutboxEvent,
    ) -> Workflow:
        """Persist workflow state and enqueue an outbox event atomically."""

    def get_workflow(self, workflow_id: UUID) -> Workflow | None:
        """Load a workflow by ID."""

    def pending_workflow_events(self, *, limit: int = 100) -> list[WorkflowOutboxEvent]:
        """Return unpublished workflow events for an outbox publisher."""

    def mark_workflow_event_published(self, event_id: UUID) -> None:
        """Mark a workflow event as published."""

    def mark_workflow_event_failed(self, event_id: UUID, error: str) -> None:
        """Record a failed workflow event publish attempt."""


class InMemoryWorkflowRepository:
    def __init__(self) -> None:
        self._workflows: dict[UUID, Workflow] = {}
        self._outbox_events: list[WorkflowOutboxEvent] = []
        self._lock = Lock()

    def save_workflow(self, workflow: Workflow) -> Workflow:
        with self._lock:
            self._workflows[workflow.id] = workflow
            return workflow

    def save_workflow_with_event(
        self,
        workflow: Workflow,
        event: WorkflowOutboxEvent,
    ) -> Workflow:
        with self._lock:
            self._workflows[workflow.id] = workflow
            if event.event_id not in {item.event_id for item in self._outbox_events}:
                self._outbox_events.append(event)
            return workflow

    def get_workflow(self, workflow_id: UUID) -> Workflow | None:
        with self._lock:
            return self._workflows.get(workflow_id)

    def pending_workflow_events(self, *, limit: int = 100) -> list[WorkflowOutboxEvent]:
        with self._lock:
            return list(self._outbox_events[: max(1, limit)])

    def mark_workflow_event_published(self, event_id: UUID) -> None:
        with self._lock:
            self._outbox_events = [
                event for event in self._outbox_events if event.event_id != event_id
            ]

    def mark_workflow_event_failed(self, event_id: UUID, error: str) -> None:
        del event_id, error
