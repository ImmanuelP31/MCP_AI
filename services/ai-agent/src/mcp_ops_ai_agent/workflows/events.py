from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from mcp_ops_schemas.events import DomainEvent

WORKFLOW_EVENTS_TOPIC = "workflow.events"
WORKFLOW_OUTBOX_SOURCE = "ai-workflow-engine"


@dataclass(frozen=True, slots=True)
class WorkflowOutboxEvent:
    event_id: UUID
    event_type: str
    aggregate_id: UUID
    payload: dict[str, object]
    created_at: datetime
    correlation_id: UUID
    source: str = WORKFLOW_OUTBOX_SOURCE
    schema_version: str = "1.0"

    @classmethod
    def create(
        cls,
        *,
        event_type: str,
        aggregate_id: UUID,
        payload: dict[str, object],
    ) -> WorkflowOutboxEvent:
        return cls(
            event_id=uuid4(),
            event_type=event_type,
            aggregate_id=aggregate_id,
            payload=payload,
            created_at=datetime.now(UTC),
            correlation_id=uuid4(),
        )

    def as_domain_event(self) -> DomainEvent:
        return DomainEvent(
            event_id=self.event_id,
            event_type=self.event_type,
            timestamp=self.created_at,
            source=self.source,
            correlation_id=self.correlation_id,
            payload=self.payload,
            schema_version=self.schema_version,
        )


class WorkflowEventPublisher(Protocol):
    def publish(
        self,
        event_type: str,
        payload: dict[str, object],
        *,
        event_id: UUID | None = None,
        correlation_id: UUID | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Publish a workflow lifecycle event."""


class KafkaProducerClient(Protocol):
    def send(self, topic: str, value: bytes) -> object:
        """Send one serialized event payload to Kafka."""


class KafkaWorkflowEventPublisher:
    def __init__(
        self,
        producer: KafkaProducerClient,
        *,
        topic: str = WORKFLOW_EVENTS_TOPIC,
    ) -> None:
        self.producer = producer
        self.topic = topic

    def publish(
        self,
        event_type: str,
        payload: dict[str, object],
        *,
        event_id: UUID | None = None,
        correlation_id: UUID | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        event = DomainEvent(
            event_id=event_id or uuid4(),
            event_type=event_type,
            timestamp=timestamp or datetime.now(UTC),
            source=WORKFLOW_OUTBOX_SOURCE,
            correlation_id=correlation_id or uuid4(),
            payload=payload,
        )
        self.producer.send(self.topic, event.model_dump_json().encode("utf-8"))


class WorkflowOutboxRepository(Protocol):
    def pending_workflow_events(self, *, limit: int = 100) -> list[WorkflowOutboxEvent]:
        """Return unpublished workflow outbox events in creation order."""

    def mark_workflow_event_published(self, event_id: UUID) -> None:
        """Mark one workflow outbox event as successfully published."""

    def mark_workflow_event_failed(self, event_id: UUID, error: str) -> None:
        """Record a failed publish attempt without deleting the outbox row."""


class WorkflowOutboxPublisher:
    def __init__(
        self,
        *,
        repository: WorkflowOutboxRepository,
        publisher: WorkflowEventPublisher,
    ) -> None:
        self.repository = repository
        self.publisher = publisher

    def drain(self, *, limit: int = 100) -> int:
        published = 0
        for event in self.repository.pending_workflow_events(limit=limit):
            try:
                self.publisher.publish(
                    event.event_type,
                    event.payload,
                    event_id=event.event_id,
                    correlation_id=event.correlation_id,
                    timestamp=event.created_at,
                )
            except Exception as exc:  # noqa: BLE001 - outbox rows remain retryable.
                self.repository.mark_workflow_event_failed(event.event_id, str(exc)[:500])
                continue
            self.repository.mark_workflow_event_published(event.event_id)
            published += 1
        return published


class InMemoryWorkflowEventPublisher:
    def __init__(self, *, fail_publish: bool = False) -> None:
        self.fail_publish = fail_publish
        self.events: list[DomainEvent] = []

    def publish(
        self,
        event_type: str,
        payload: dict[str, object],
        *,
        event_id: UUID | None = None,
        correlation_id: UUID | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        if self.fail_publish:
            raise RuntimeError("workflow event publisher unavailable")
        self.events.append(
            DomainEvent(
                event_id=event_id or uuid4(),
                event_type=event_type,
                timestamp=timestamp or datetime.now(UTC),
                source=WORKFLOW_OUTBOX_SOURCE,
                correlation_id=correlation_id or uuid4(),
                payload=payload,
            )
        )
