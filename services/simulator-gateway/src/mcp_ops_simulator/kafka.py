from __future__ import annotations

from typing import Protocol

from mcp_ops_schemas.events import DomainEvent


class KafkaProducerClient(Protocol):
    def send(self, topic: str, value: bytes) -> object:
        pass


class KafkaEventPublisher:
    """Adapter for publishing simulator domain events to a Kafka client."""

    def __init__(self, producer: KafkaProducerClient) -> None:
        self._producer = producer

    def publish(self, topic: str, event: DomainEvent) -> None:
        payload = event.model_dump_json().encode("utf-8")
        self._producer.send(topic, payload)

