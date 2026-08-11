from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class DeviceStatus(StrEnum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    OFFLINE = "OFFLINE"


class ServiceState(StrEnum):
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    STOPPED = "STOPPED"
    CRASHED = "CRASHED"


class AlertSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class FailureScenario(StrEnum):
    SERVICE_CRASH = "service-crash"
    CPU_SATURATION = "cpu-saturation"
    MEMORY_PRESSURE = "memory-pressure"
    PACKET_LOSS = "packet-loss"
    NETWORK_TIMEOUT = "network-timeout"
    SENSOR_INITIALIZATION_FAILURE = "sensor-initialization-failure"
    TELEMETRY_DELAY = "telemetry-delay"
    DISK_CAPACITY_WARNING = "disk-capacity-warning"


@dataclass(slots=True)
class DeviceService:
    name: str
    state: ServiceState
    version: str
    last_restart_at: datetime

    def as_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        payload["last_restart_at"] = self.last_restart_at.isoformat()
        return payload


@dataclass(slots=True)
class SimulatedDevice:
    internal_id: uuid.UUID
    device_id: str
    serial_number: str
    model: str
    location: str
    site: str
    firmware_version: str
    status: DeviceStatus
    health_score: float
    last_seen: datetime
    boot_time: datetime
    services: dict[str, DeviceService] = field(default_factory=dict)
    active_scenario: FailureScenario | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "internal_id": str(self.internal_id),
            "device_id": self.device_id,
            "serial_number": self.serial_number,
            "model": self.model,
            "location": self.location,
            "site": self.site,
            "firmware_version": self.firmware_version,
            "status": self.status.value,
            "health_score": self.health_score,
            "last_seen": self.last_seen.isoformat(),
            "boot_time": self.boot_time.isoformat(),
            "services": [service.as_payload() for service in self.services.values()],
            "active_scenario": self.active_scenario.value if self.active_scenario else None,
        }


@dataclass(frozen=True, slots=True)
class DeviceTelemetry:
    telemetry_id: uuid.UUID
    device_id: str
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    temperature_c: float
    network_latency_ms: float
    packet_loss_percent: float
    disk_percent: float
    uptime_seconds: int
    service_states: dict[str, ServiceState]
    delayed: bool = False

    def as_payload(self) -> dict[str, Any]:
        return {
            "telemetry_id": str(self.telemetry_id),
            "device_id": self.device_id,
            "timestamp": self.timestamp.isoformat(),
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "temperature_c": self.temperature_c,
            "network_latency_ms": self.network_latency_ms,
            "packet_loss_percent": self.packet_loss_percent,
            "disk_percent": self.disk_percent,
            "uptime_seconds": self.uptime_seconds,
            "service_states": {name: state.value for name, state in self.service_states.items()},
            "delayed": self.delayed,
        }


@dataclass(frozen=True, slots=True)
class DeviceAlert:
    alert_id: uuid.UUID
    device_id: str
    severity: AlertSeverity
    message: str
    error_code: str
    timestamp: datetime

    def as_payload(self) -> dict[str, Any]:
        return {
            "alert_id": str(self.alert_id),
            "device_id": self.device_id,
            "severity": self.severity.value,
            "message": self.message,
            "error_code": self.error_code,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class SimulatedIncident:
    incident_id: uuid.UUID
    device_id: str
    title: str
    severity: AlertSeverity
    status: str
    created_at: datetime
    alert_id: uuid.UUID

    def as_payload(self) -> dict[str, Any]:
        return {
            "incident_id": str(self.incident_id),
            "device_id": self.device_id,
            "title": self.title,
            "severity": self.severity.value,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "alert_id": str(self.alert_id),
        }
