from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from mcp_ops_schemas.events import DomainEvent

WORKFLOW_EVENTS_TOPIC = "workflow.events"


class WorkflowEventPublisher(Protocol):
    def publish(self, event_type: str, payload: dict[str, object]) -> None:
        """Publish a workflow lifecycle event."""


class InMemoryWorkflowEventPublisher:
    def __init__(self, *, fail_publish: bool = False) -> None:
        self.fail_publish = fail_publish
        self.events: list[DomainEvent] = []

    def publish(self, event_type: str, payload: dict[str, object]) -> None:
        if self.fail_publish:
            raise RuntimeError("workflow event publisher unavailable")
        self.events.append(
            DomainEvent(
                event_id=uuid4(),
                event_type=event_type,
                timestamp=datetime.now(UTC),
                source="ai-workflow-engine",
                correlation_id=uuid4(),
                payload=payload,
            )
        )
