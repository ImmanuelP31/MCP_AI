from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from mcp_ops_simulator.clock import DEFAULT_TEST_TIME
from mcp_ops_simulator.consumers import evaluate_health
from mcp_ops_simulator.models import ServiceState
from mcp_ops_simulator.registry import DeviceNotFoundError, DeviceRegistry

from mcp_ops_mcp.diagnostics import DiagnosticReport, RuleBasedDiagnosticsEngine
from mcp_ops_mcp.errors import (
    DeviceNotFound,
    DocumentNotFound,
    InvalidConfiguration,
    TicketNotFound,
)
from mcp_ops_mcp.knowledge import EngineeringKnowledgeRepository
from mcp_ops_mcp.schemas import StructuredOutput

ALLOWED_CONFIGURATION_KEYS = {
    "telemetry_interval_seconds",
    "diagnostics_enabled",
    "firmware_channel",
    "packet_loss_threshold",
}


def default_registry() -> DeviceRegistry:
    return DeviceRegistry.seeded(base_time=DEFAULT_TEST_TIME)


class DeviceDomainService:
    def __init__(self, registry: DeviceRegistry | None = None) -> None:
        self.registry = registry or default_registry()
        self._configuration: dict[str, dict[str, str | int | float | bool]] = {
            device.device_id: {
                "telemetry_interval_seconds": 30,
                "diagnostics_enabled": True,
                "firmware_channel": "stable",
                "packet_loss_threshold": 10.0,
            }
            for device in self.registry.list_devices()
        }

    def list_devices(self, limit: int) -> StructuredOutput:
        devices = [device.as_payload() for device in self.registry.list_devices()[:limit]]
        return StructuredOutput(ok=True, data={"count": len(devices), "devices": devices})

    def get_device(self, device_id: str) -> StructuredOutput:
        device = self._device(device_id)
        return StructuredOutput(ok=True, data={"device": device.as_payload()})

    def get_status(self, device_id: str) -> StructuredOutput:
        device = self._device(device_id)
        return StructuredOutput(
            ok=True,
            data={"device_id": device.device_id, "status": device.status.value},
        )

    def get_health(self, device_id: str) -> StructuredOutput:
        device = self._device(device_id)
        return StructuredOutput(
            ok=True,
            data={
                "device_id": device.device_id,
                "status": device.status.value,
                "health_score": device.health_score,
            },
        )

    def get_telemetry(self, device_id: str, limit: int) -> StructuredOutput:
        telemetry = [
            self.registry.telemetry_for(device_id, DEFAULT_TEST_TIME).as_payload()
            for _ in range(limit)
        ]
        return StructuredOutput(ok=True, data={"device_id": device_id, "telemetry": telemetry})

    def get_configuration(self, device_id: str) -> StructuredOutput:
        self._device(device_id)
        return StructuredOutput(
            ok=True,
            data={"device_id": device_id, "configuration": self._configuration[device_id]},
        )

    def get_services(self, device_id: str) -> StructuredOutput:
        device = self._device(device_id)
        return StructuredOutput(
            ok=True,
            data={
                "device_id": device_id,
                "services": [s.as_payload() for s in device.services.values()],
            },
        )

    def run_diagnostics(self, device_id: str, checks: list[str]) -> StructuredOutput:
        telemetry = self.registry.telemetry_for(device_id, DEFAULT_TEST_TIME)
        status, health_score = evaluate_health(telemetry.as_payload())
        return StructuredOutput(
            ok=True,
            data={
                "device_id": device_id,
                "checks": checks,
                "status": "FAILED" if status.value == "CRITICAL" else "SUCCEEDED",
                "health_status": status.value,
                "health_score": health_score,
                "summary": f"{device_id} diagnostic run completed with {status.value} health.",
            },
        )

    def restart_device(self, device_id: str, reason: str) -> StructuredOutput:
        device = self.registry.clear_scenario(device_id, DEFAULT_TEST_TIME)
        return StructuredOutput(
            ok=True,
            data={"device_id": device.device_id, "operation": "restart_device", "reason": reason},
        )

    def restart_service(self, device_id: str, service_name: str, reason: str) -> StructuredOutput:
        device = self._device(device_id)
        try:
            device.services[service_name].state = ServiceState.RUNNING
        except KeyError as exc:
            raise DeviceNotFound(f"Service {service_name} was not found on {device_id}.") from exc
        return StructuredOutput(
            ok=True,
            data={
                "device_id": device_id,
                "service_name": service_name,
                "operation": "restart_service",
                "reason": reason,
            },
        )

    def update_configuration(
        self,
        device_id: str,
        patch: dict[str, str | int | float | bool],
        reason: str,
    ) -> StructuredOutput:
        self._device(device_id)
        validated_patch = _validate_configuration_patch(patch)
        self._configuration[device_id].update(validated_patch)
        return StructuredOutput(
            ok=True,
            data={
                "device_id": device_id,
                "operation": "update_device_configuration",
                "configuration": self._configuration[device_id],
                "reason": reason,
            },
        )

    def _device(self, device_id: str) -> Any:
        try:
            return self.registry.get_device(device_id)
        except DeviceNotFoundError as exc:
            raise DeviceNotFound(f"Device {device_id} was not found.") from exc


class DiagnosticsDomainService:
    def __init__(
        self,
        device_service: DeviceDomainService | None = None,
        knowledge_repository: EngineeringKnowledgeRepository | None = None,
    ) -> None:
        self.device_service = device_service or DeviceDomainService()
        self.knowledge_repository = knowledge_repository or EngineeringKnowledgeRepository()
        self._logs = _seed_logs()
        self._historical_incidents = _seed_historical_incidents()
        self._engine = RuleBasedDiagnosticsEngine()

    def search_logs(
        self,
        device_id: str,
        severity: str | None,
        query: str | None,
        limit: int,
    ) -> StructuredOutput:
        self.device_service._device(device_id)
        logs = [log for log in self._logs if log["device_id"] == device_id]
        if severity:
            logs = [log for log in logs if log["severity"] == severity]
        if query:
            logs = [log for log in logs if query.lower() in str(log["message"]).lower()]
        return StructuredOutput(ok=True, data={"logs": logs[:limit]})

    def recent_errors(self, device_id: str) -> StructuredOutput:
        return self.search_logs(device_id, "ERROR", None, 20)

    def error_details(self, error_code: str) -> StructuredOutput:
        details = ERROR_CATALOG.get(error_code)
        if details is None:
            details = {"error_code": error_code, "description": "No detailed catalog entry found."}
        return StructuredOutput(ok=True, data={"error": details})

    def service_health(self, device_id: str, service_name: str) -> StructuredOutput:
        device = self.device_service._device(device_id)
        service = device.services.get(service_name)
        if service is None:
            raise DeviceNotFound(f"Service {service_name} was not found on {device_id}.")
        return StructuredOutput(
            ok=True,
            data={
                "device_id": device_id,
                "service_name": service_name,
                "state": service.state.value,
            },
        )

    def resource_usage(self, device_id: str) -> StructuredOutput:
        telemetry = self.device_service.registry.telemetry_for(device_id, DEFAULT_TEST_TIME)
        return StructuredOutput(ok=True, data={"resource_usage": telemetry.as_payload()})

    def similar_incidents(self, device_id: str) -> StructuredOutput:
        self.device_service._device(device_id)
        return StructuredOutput(
            ok=True,
            data={
                "incidents": [
                    incident
                    for incident in self._historical_incidents
                    if incident["device_id"] in {device_id, "ANY"}
                ]
            },
        )

    def run_check(self, device_id: str, check_name: str) -> StructuredOutput:
        report = self._diagnostic_report(device_id)
        return StructuredOutput(
            ok=True,
            data={
                "check_name": check_name,
                "diagnostic_report": report.as_payload(),
            },
        )

    def summary(self, device_id: str) -> StructuredOutput:
        report = self._diagnostic_report(device_id)
        return StructuredOutput(
            ok=True,
            data={
                "device_id": device_id,
                "diagnostic_report": report.as_payload(),
                "summary": "; ".join(report.possible_causes),
            },
        )

    def _diagnostic_report(self, device_id: str) -> DiagnosticReport:
        device = self.device_service._device(device_id)
        telemetry = self.device_service.registry.telemetry_for(device_id, DEFAULT_TEST_TIME)
        recent_errors = [log for log in self._logs if log["device_id"] == device_id]
        knowledge_references = self.knowledge_repository.references_for_signals(
            _diagnostic_signal_candidates(recent_errors)
        )
        return self._engine.diagnose(
            device,
            telemetry,
            recent_errors,
            self._historical_incidents,
            knowledge_references,
        )


class KnowledgeDomainService:
    def __init__(self, repository: EngineeringKnowledgeRepository | None = None) -> None:
        self.repository = repository or EngineeringKnowledgeRepository()

    def search(self, query: str, limit: int) -> StructuredOutput:
        results = self.repository.search(query, limit=limit)
        return StructuredOutput(
            ok=True,
            data={"documents": [item.document.summary_payload(item.score) for item in results]},
        )

    def document(self, document_id: str) -> StructuredOutput:
        document = self.repository.get(document_id)
        if document is None:
            raise DocumentNotFound(f"Document {document_id} was not found.")
        return StructuredOutput(ok=True, data={"document": document.as_payload()})

    def procedure(self, procedure_id: str) -> StructuredOutput:
        document = self.repository.get_procedure(procedure_id)
        if document is None:
            raise DocumentNotFound(f"Procedure {procedure_id} was not found.")
        return StructuredOutput(ok=True, data={"procedure": document.as_payload()})

    def troubleshooting(self, error_code: str, device_model: str | None) -> StructuredOutput:
        matches = self.repository.troubleshooting_steps(error_code, device_model)
        steps = [step for match in matches for step in match["steps"]]
        if not steps:
            steps = [
                "Collect recent device telemetry.",
                "Review service health and recent errors.",
                "Create a ticket if diagnostics confirm impact.",
            ]
        return StructuredOutput(
            ok=True,
            data={
                "error_code": error_code,
                "device_model": device_model,
                "steps": steps,
                "references": matches,
            },
        )

    def configuration_guides(self, query: str, limit: int) -> StructuredOutput:
        results = self.repository.search(
            query or "configuration",
            limit=limit,
            document_type="CONFIGURATION_GUIDE",
        )
        return StructuredOutput(
            ok=True,
            data={"documents": [item.document.summary_payload(item.score) for item in results]},
        )


@dataclass
class Ticket:
    ticket_id: str
    title: str
    description: str
    device_id: str
    priority: str
    status: str
    assignee: str | None
    team: str
    created_by: str
    diagnostic_evidence: dict[str, Any] = field(default_factory=dict)


class TicketDomainService:
    def __init__(self, device_service: DeviceDomainService | None = None) -> None:
        self.device_service = device_service or DeviceDomainService()
        self._tickets: dict[str, Ticket] = {
            "TCK-014": Ticket(
                ticket_id="TCK-014",
                title="Maintenance review for SIM-014",
                description="Investigate telemetry timeout and sensor ingestor failure.",
                device_id="SIM-014",
                priority="CRITICAL",
                status="OPEN",
                assignee="operator@example.internal",
                team="Simulator Operations",
                created_by="seed",
                diagnostic_evidence={"error_code": "E-SENSOR-INIT"},
            )
        }

    def create(self, payload: dict[str, Any], actor_role: str) -> StructuredOutput:
        self.device_service._device(str(payload["device_id"]))
        ticket_id = f"TCK-{uuid.uuid5(uuid.NAMESPACE_URL, str(payload))!s}"[:12]
        ticket = Ticket(
            ticket_id=ticket_id,
            title=str(payload["title"]),
            description=str(payload["description"]),
            device_id=str(payload["device_id"]),
            priority=str(payload["priority"]),
            status="OPEN",
            assignee=None,
            team=str(payload["team"]),
            created_by=actor_role,
            diagnostic_evidence=dict(payload.get("diagnostic_evidence", {})),
        )
        self._tickets[ticket.ticket_id] = ticket
        return StructuredOutput(ok=True, data={"ticket": ticket.__dict__})

    def get(self, ticket_id: str) -> StructuredOutput:
        return StructuredOutput(ok=True, data={"ticket": self._ticket(ticket_id).__dict__})

    def update(
        self,
        ticket_id: str,
        status: str | None,
        priority: str | None,
        description: str | None,
    ) -> StructuredOutput:
        ticket = self._ticket(ticket_id)
        if status:
            ticket.status = status
        if priority:
            ticket.priority = priority
        if description:
            ticket.description = description
        return StructuredOutput(ok=True, data={"ticket": ticket.__dict__})

    def assign(self, ticket_id: str, assignee: str) -> StructuredOutput:
        ticket = self._ticket(ticket_id)
        ticket.assignee = assignee
        return StructuredOutput(ok=True, data={"ticket": ticket.__dict__})

    def search(
        self,
        query: str | None,
        status: str | None,
        device_id: str | None,
        limit: int,
    ) -> StructuredOutput:
        tickets = list(self._tickets.values())
        if query:
            tickets = [ticket for ticket in tickets if query.lower() in ticket.title.lower()]
        if status:
            tickets = [ticket for ticket in tickets if ticket.status == status]
        if device_id:
            tickets = [ticket for ticket in tickets if ticket.device_id == device_id]
        return StructuredOutput(
            ok=True,
            data={"tickets": [ticket.__dict__ for ticket in tickets[:limit]]},
        )

    def open_tickets(self, limit: int) -> StructuredOutput:
        return self.search(None, "OPEN", None, limit)

    def _ticket(self, ticket_id: str) -> Ticket:
        try:
            return self._tickets[ticket_id]
        except KeyError as exc:
            raise TicketNotFound(f"Ticket {ticket_id} was not found.") from exc


def _seed_logs() -> list[dict[str, Any]]:
    return [
        {
            "timestamp": DEFAULT_TEST_TIME.isoformat(),
            "device_id": "SIM-014",
            "service": "sensor-ingestor",
            "severity": "ERROR",
            "message": "Sensor initialization failed during telemetry cycle.",
            "error_code": "E-SENSOR-INIT",
            "correlation_id": "corr-sim-014",
        },
        {
            "timestamp": DEFAULT_TEST_TIME.isoformat(),
            "device_id": "SIM-014",
            "service": "telemetry-agent",
            "severity": "CRITICAL",
            "message": "Network timeout while publishing telemetry.",
            "error_code": "E-NET-TIMEOUT",
            "correlation_id": "corr-sim-014",
        },
        {
            "timestamp": DEFAULT_TEST_TIME.isoformat(),
            "device_id": "SIM-014",
            "service": "sensor-ingestor",
            "severity": "ERROR",
            "message": "sensor-ingestor crash detected by supervisor.",
            "error_code": "E-SERVICE-CRASH",
            "correlation_id": "corr-sim-014",
        },
        {
            "timestamp": DEFAULT_TEST_TIME.isoformat(),
            "device_id": "SIM-014",
            "service": "diagnostic-runner",
            "severity": "ERROR",
            "message": "Process response latency high while CPU is saturated.",
            "error_code": "E-CPU-LATENCY",
            "correlation_id": "corr-sim-014",
        },
    ]


def _seed_historical_incidents() -> list[dict[str, Any]]:
    return [
        {
            "incident_id": "INC-NET-001",
            "device_id": "ANY",
            "title": "Packet loss with network timeout errors",
            "signals": ["packet_loss", "network_timeout_error", "degraded_service"],
        },
        {
            "incident_id": "INC-CPU-001",
            "device_id": "ANY",
            "title": "CPU saturation with high response latency",
            "signals": ["cpu_percent", "high_latency"],
        },
        {
            "incident_id": "INC-SVC-001",
            "device_id": "ANY",
            "title": "Service crash with supervisor crash log",
            "signals": ["crashed_service", "crash_log"],
        },
        {
            "incident_id": "INC-SENSOR-001",
            "device_id": "ANY",
            "title": "Sensor initialization failure",
            "signals": ["sensor_initialization_error", "crashed_service"],
        },
        {
            "incident_id": "INC-DISK-001",
            "device_id": "ANY",
            "title": "Disk capacity warning",
            "signals": ["disk_percent"],
        },
    ]


def _diagnostic_signal_candidates(recent_errors: list[dict[str, Any]]) -> set[str]:
    signals = {
        "packet_loss",
        "network_timeout_error",
        "degraded_service",
        "cpu_percent",
        "high_latency",
        "process_latency_error",
        "memory_percent",
        "temperature_c",
        "crashed_service",
        "crash_log",
        "sensor_initialization_error",
        "disk_percent",
        "telemetry_delay",
    }
    error_codes = {str(error.get("error_code")) for error in recent_errors}
    if "E-NET-TIMEOUT" in error_codes:
        signals.add("network_timeout_error")
    if "E-SENSOR-INIT" in error_codes:
        signals.add("sensor_initialization_error")
    return signals


def _validate_configuration_patch(
    patch: dict[str, str | int | float | bool],
) -> dict[str, str | int | float | bool]:
    rejected = sorted(set(patch) - ALLOWED_CONFIGURATION_KEYS)
    if rejected:
        raise InvalidConfiguration(
            "Unsupported configuration keys: " + ", ".join(rejected) + "."
        )
    validated: dict[str, str | int | float | bool] = {}
    for key, value in patch.items():
        if key == "telemetry_interval_seconds":
            if not isinstance(value, int) or isinstance(value, bool):
                raise InvalidConfiguration(
                    "telemetry_interval_seconds must be an integer from 5 to 3600."
                )
            if not 5 <= value <= 3600:
                raise InvalidConfiguration(
                    "telemetry_interval_seconds must be an integer from 5 to 3600."
                )
        elif key == "diagnostics_enabled":
            if not isinstance(value, bool):
                raise InvalidConfiguration("diagnostics_enabled must be a boolean.")
        elif key == "firmware_channel":
            if not isinstance(value, str) or value not in {"stable", "candidate"}:
                raise InvalidConfiguration("firmware_channel must be stable or candidate.")
        elif key == "packet_loss_threshold":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise InvalidConfiguration("packet_loss_threshold must be numeric from 0 to 100.")
            if not 0 <= value <= 100:
                raise InvalidConfiguration("packet_loss_threshold must be numeric from 0 to 100.")
        validated[key] = value
    return validated


ERROR_CATALOG: dict[str, dict[str, str]] = {
    "E-SENSOR-INIT": {
        "error_code": "E-SENSOR-INIT",
        "description": "Sensor initialization failure.",
        "recommended_procedure": "kb-sensor-init",
    },
    "E-NET-TIMEOUT": {
        "error_code": "E-NET-TIMEOUT",
        "description": "Telemetry network timeout.",
        "recommended_procedure": "kb-service-restart",
    },
}
