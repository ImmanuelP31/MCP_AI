from __future__ import annotations

from threading import Lock
from typing import Protocol
from uuid import UUID

from mcp_ops_ai_agent.workflows.models import Workflow


class WorkflowRepositoryProtocol(Protocol):
    def save_workflow(self, workflow: Workflow) -> Workflow:
        """Persist workflow state."""

    def get_workflow(self, workflow_id: UUID) -> Workflow | None:
        """Load a workflow by ID."""


class InMemoryWorkflowRepository:
    def __init__(self) -> None:
        self._workflows: dict[UUID, Workflow] = {}
        self._lock = Lock()

    def save_workflow(self, workflow: Workflow) -> Workflow:
        with self._lock:
            self._workflows[workflow.id] = workflow
            return workflow

    def get_workflow(self, workflow_id: UUID) -> Workflow | None:
        with self._lock:
            return self._workflows.get(workflow_id)
