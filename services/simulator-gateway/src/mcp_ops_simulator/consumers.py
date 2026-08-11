from __future__ import annotations

from datetime import datetime

from mcp_ops_observability.metrics import set_device_health
from mcp_ops_schemas.events import DomainEvent

from mcp_ops_simulator.events import (
    DEVICE_ALERT_TOPIC,
    DEVICE_HEALTH_TOPIC,
    INCIDENT_CREATED_TOPIC,
    EventPublisher,
    alert_event,
    health_event,
    incident_event,
)
from mcp_ops_simulator.ids import deterministic_uuid
from mcp_ops_simulator.models import (
    AlertSeverity,
    DeviceAlert,
    DeviceStatus,
    ServiceState,
    SimulatedIncident,
)
from mcp_ops_simulator.registry import DeviceRegistry


class TelemetryConsumer:
    def __init__(self, registry: DeviceRegistry, publisher: EventPublisher) -> None:
        self.registry = registry
        self.publisher = publisher
        self._processed_ids: set[str] = set()

    def process(self, event: DomainEvent) -> list[DomainEvent]:
        event_key = str(event.event_id)
        if event_key in self._processed_ids:
            return []
        self._processed_ids.add(event_key)

        payload = event.payload
        device_id = str(payload["device_id"])
        timestamp = event.timestamp
        status, health_score = evaluate_health(payload)
        self.registry.update_health(device_id, status, health_score, timestamp)
        set_device_health(device_id, status.value, health_score)

        published: list[DomainEvent] = []
        health = health_event(device_id, status.value, health_score, timestamp)
        self.publisher.publish(DEVICE_HEALTH_TOPIC, health)
        published.append(health)

        alert = build_alert(payload, status, timestamp)
        if alert is not None:
            alert_domain_event = alert_event(alert)
            self.publisher.publish(DEVICE_ALERT_TOPIC, alert_domain_event)
            published.append(alert_domain_event)

        if alert is not None and alert.severity == AlertSeverity.CRITICAL:
            incident = build_incident(alert, timestamp)
            incident_domain_event = incident_event(incident)
            self.publisher.publish(INCIDENT_CREATED_TOPIC, incident_domain_event)
            published.append(incident_domain_event)

        return published


def evaluate_health(payload: dict[str, object]) -> tuple[DeviceStatus, float]:
    cpu = _float(payload["cpu_percent"])
    memory = _float(payload["memory_percent"])
    temperature = _float(payload["temperature_c"])
    latency = _float(payload["network_latency_ms"])
    packet_loss = _float(payload["packet_loss_percent"])
    disk = _float(payload["disk_percent"])
    delayed = bool(payload["delayed"])
    service_states = _service_states(payload)

    critical_conditions = [
        cpu >= 95,
        memory >= 95,
        latency >= 3000,
        packet_loss >= 50,
        temperature >= 80,
        ServiceState.CRASHED in service_states.values(),
    ]
    warning_conditions = [
        cpu >= 85,
        memory >= 85,
        packet_loss >= 10,
        disk >= 85,
        delayed,
        ServiceState.DEGRADED in service_states.values(),
        ServiceState.STOPPED in service_states.values(),
    ]
    if any(critical_conditions):
        return DeviceStatus.CRITICAL, 18.0
    if any(warning_conditions):
        return DeviceStatus.WARNING, 62.0
    return DeviceStatus.HEALTHY, 96.0


def build_alert(
    payload: dict[str, object],
    status: DeviceStatus,
    timestamp: datetime,
) -> DeviceAlert | None:
    if status == DeviceStatus.HEALTHY:
        return None
    device_id = str(payload["device_id"])
    error_code, message = _alert_reason(payload)
    severity = AlertSeverity.CRITICAL if status == DeviceStatus.CRITICAL else AlertSeverity.WARNING
    return DeviceAlert(
        alert_id=deterministic_uuid(f"alert:{device_id}:{error_code}:{timestamp.isoformat()}"),
        device_id=device_id,
        severity=severity,
        message=message,
        error_code=error_code,
        timestamp=timestamp,
    )


def build_incident(alert: DeviceAlert, timestamp: datetime) -> SimulatedIncident:
    return SimulatedIncident(
        incident_id=deterministic_uuid(
            f"incident:{alert.device_id}:{alert.error_code}:{timestamp.isoformat()}"
        ),
        device_id=alert.device_id,
        title=f"{alert.device_id} threshold breach: {alert.error_code}",
        severity=alert.severity,
        status="OPEN",
        created_at=timestamp,
        alert_id=alert.alert_id,
    )


def _alert_reason(payload: dict[str, object]) -> tuple[str, str]:
    service_states = _service_states(payload)
    if ServiceState.CRASHED in service_states.values():
        return "E-SERVICE-CRASH", "A simulator service is crashed."
    if _float(payload["network_latency_ms"]) >= 3000:
        return "E-NET-TIMEOUT", "Network timeout threshold exceeded."
    if _float(payload["packet_loss_percent"]) >= 10:
        return "E-NET-LOSS", "Packet loss threshold exceeded."
    if _float(payload["cpu_percent"]) >= 85:
        return "E-CPU-SATURATION", "CPU saturation threshold exceeded."
    if _float(payload["memory_percent"]) >= 85:
        return "E-MEM-PRESSURE", "Memory pressure threshold exceeded."
    if _float(payload["disk_percent"]) >= 85:
        return "E-DISK-CAPACITY", "Disk capacity warning threshold exceeded."
    if bool(payload["delayed"]):
        return "E-TELEMETRY-DELAY", "Telemetry delay threshold exceeded."
    return "E-DEVICE-WARNING", "Device health degraded."


def _float(value: object) -> float:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        return float(value)
    raise TypeError(f"Expected numeric telemetry value, got {type(value).__name__}")


def _service_states(payload: dict[str, object]) -> dict[str, ServiceState]:
    raw_states = payload["service_states"]
    if not isinstance(raw_states, dict):
        raise TypeError("service_states must be an object")
    return {str(name): ServiceState(str(state)) for name, state in raw_states.items()}
