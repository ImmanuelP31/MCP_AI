from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from mcp_ops_schemas.events import DomainEvent

from mcp_ops_simulator.ids import event_id
from mcp_ops_simulator.models import DeviceAlert, DeviceTelemetry, SimulatedIncident

DEVICE_TELEMETRY_TOPIC = "device.telemetry"
DEVICE_HEALTH_TOPIC = "device.health"
DEVICE_ALERT_TOPIC = "device.alert"
INCIDENT_CREATED_TOPIC = "incident.created"
SIMULATOR_SOURCE = "simulator-gateway"
SYSTEM_ACTOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


class EventPublisher(Protocol):
    def publish(self, topic: str, event: DomainEvent) -> None:
        pass


class InMemoryEventBus:
    def __init__(self) -> None:
        self._events: dict[str, list[DomainEvent]] = defaultdict(list)

    def publish(self, topic: str, event: DomainEvent) -> None:
        self._events[topic].append(event)

    def topic_events(self, topic: str) -> Sequence[DomainEvent]:
        return tuple(self._events[topic])

    def all_events(self) -> dict[str, Sequence[DomainEvent]]:
        return {topic: tuple(events) for topic, events in self._events.items()}


def telemetry_event(telemetry: DeviceTelemetry) -> DomainEvent:
    return DomainEvent(
        event_id=event_id(DEVICE_TELEMETRY_TOPIC, telemetry.device_id, telemetry.timestamp),
        event_type="device.telemetry.recorded",
        timestamp=telemetry.timestamp,
        source=SIMULATOR_SOURCE,
        correlation_id=event_id("correlation", telemetry.device_id, telemetry.timestamp),
        actor_id=SYSTEM_ACTOR_ID,
        payload=telemetry.as_payload(),
    )


def health_event(
    device_id: str,
    status: str,
    health_score: float,
    timestamp: datetime,
) -> DomainEvent:
    return DomainEvent(
        event_id=event_id(DEVICE_HEALTH_TOPIC, device_id, timestamp),
        event_type="device.health.updated",
        timestamp=timestamp,
        source=SIMULATOR_SOURCE,
        correlation_id=event_id("correlation", device_id, timestamp),
        actor_id=SYSTEM_ACTOR_ID,
        payload={
            "device_id": device_id,
            "status": status,
            "health_score": health_score,
        },
    )


def alert_event(alert: DeviceAlert) -> DomainEvent:
    return DomainEvent(
        event_id=event_id(DEVICE_ALERT_TOPIC, alert.device_id, alert.timestamp),
        event_type="device.alert.generated",
        timestamp=alert.timestamp,
        source=SIMULATOR_SOURCE,
        correlation_id=event_id("correlation", alert.device_id, alert.timestamp),
        actor_id=SYSTEM_ACTOR_ID,
        payload=alert.as_payload(),
    )


def incident_event(incident: SimulatedIncident) -> DomainEvent:
    return DomainEvent(
        event_id=event_id(INCIDENT_CREATED_TOPIC, incident.device_id, incident.created_at),
        event_type="incident.created",
        timestamp=incident.created_at,
        source=SIMULATOR_SOURCE,
        correlation_id=event_id("correlation", incident.device_id, incident.created_at),
        actor_id=SYSTEM_ACTOR_ID,
        payload=incident.as_payload(),
    )
