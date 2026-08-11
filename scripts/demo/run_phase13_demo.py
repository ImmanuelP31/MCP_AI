# ruff: noqa: E402

from __future__ import annotations

import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

ROOT = Path(__file__).resolve().parents[2]
for source_root in [
    ROOT / "packages" / "auth" / "src",
    ROOT / "packages" / "common" / "src",
    ROOT / "packages" / "mcp" / "src",
    ROOT / "packages" / "observability" / "src",
    ROOT / "packages" / "policy" / "src",
    ROOT / "packages" / "schemas" / "src",
    ROOT / "services" / "ai-agent" / "src",
    ROOT / "services" / "device-mcp" / "src",
    ROOT / "services" / "diagnostics-mcp" / "src",
    ROOT / "services" / "knowledge-mcp" / "src",
    ROOT / "services" / "mcp-gateway" / "src",
    ROOT / "services" / "simulator-gateway" / "src",
    ROOT / "services" / "ticket-mcp" / "src",
]:
    sys.path.insert(0, str(source_root))

from mcp_ops_ai_agent.gateway import GatewayClient
from mcp_ops_ai_agent.service import AiEngineeringAgent
from mcp_ops_device_mcp.server import create_dispatcher as create_device_dispatcher
from mcp_ops_diagnostics_mcp.server import create_dispatcher as create_diagnostics_dispatcher
from mcp_ops_knowledge_mcp.server import create_dispatcher as create_knowledge_dispatcher
from mcp_ops_mcp.services import (
    DeviceDomainService,
    DiagnosticsDomainService,
    KnowledgeDomainService,
    TicketDomainService,
)
from mcp_ops_mcp_gateway.models import GatewayToolRequest, GatewayToolResponse
from mcp_ops_mcp_gateway.service import McpGateway
from mcp_ops_mcp_gateway.stores import ApprovalStore
from mcp_ops_simulator.clock import DEFAULT_TEST_TIME
from mcp_ops_simulator.consumers import TelemetryConsumer
from mcp_ops_simulator.events import (
    DEVICE_ALERT_TOPIC,
    DEVICE_TELEMETRY_TOPIC,
    INCIDENT_CREATED_TOPIC,
    InMemoryEventBus,
)
from mcp_ops_simulator.models import FailureScenario
from mcp_ops_simulator.producer import TelemetryProducer
from mcp_ops_simulator.registry import DeviceRegistry
from mcp_ops_ticket_mcp.server import create_dispatcher as create_ticket_dispatcher

DEMO_DEVICE_ID = "SIM-014"
DEMO_SERVICE = "telemetry-agent"


class LocalGatewayClient(GatewayClient):
    def __init__(self, gateway: McpGateway) -> None:
        self.gateway = gateway

    def call_tool(self, request: GatewayToolRequest) -> GatewayToolResponse:
        return self.gateway.call_tool(request)


def main() -> None:
    environment = DemoEnvironment()
    transcript = {
        "demo_title": "Phase 13 deterministic engineering operations demo",
        "timestamp": DEFAULT_TEST_TIME.isoformat(),
        "demos": [
            environment.demo_1_fleet_monitoring(),
            environment.demo_2_incident_investigation(),
            environment.demo_3_knowledge_assisted_diagnosis(),
            environment.demo_4_ticket_automation(),
            environment.demo_5_high_risk_operation(),
        ],
    }
    print(json.dumps(transcript, indent=2, sort_keys=True))


class DemoEnvironment:
    def __init__(self) -> None:
        self.registry = DeviceRegistry.seeded(base_time=DEFAULT_TEST_TIME)
        self.event_bus = InMemoryEventBus()
        self.producer = TelemetryProducer(self.registry, self.event_bus)
        self.consumer = TelemetryConsumer(self.registry, self.event_bus)
        self.device_service = DeviceDomainService(self.registry)
        self.diagnostics_service = DiagnosticsDomainService(self.device_service)
        self.knowledge_service = KnowledgeDomainService()
        self.ticket_service = TicketDomainService(self.device_service)
        self.gateway = McpGateway(
            approvals=ApprovalStore(
                id_factory=lambda: uuid5(NAMESPACE_URL, "phase-13:restart-service-approval")
            ),
            clock=lambda: DEFAULT_TEST_TIME,
        )
        self.gateway._dispatchers = {  # noqa: SLF001 - demo wiring shares deterministic state.
            "device": create_device_dispatcher(self.device_service),
            "diagnostics": create_diagnostics_dispatcher(self.diagnostics_service),
            "knowledge": create_knowledge_dispatcher(self.knowledge_service),
            "ticket": create_ticket_dispatcher(self.ticket_service),
        }
        self.agent = AiEngineeringAgent(gateway_client=LocalGatewayClient(self.gateway))

    def demo_1_fleet_monitoring(self) -> dict[str, Any]:
        devices = self.registry.list_devices()
        distribution = Counter(device.status.value for device in devices)
        telemetry = self.registry.telemetry_for(DEMO_DEVICE_ID, DEFAULT_TEST_TIME).as_payload()
        return {
            "name": "DEMO 1 - Fleet monitoring",
            "dashboard_route": "/dashboard",
            "device_count": len(devices),
            "distribution": _distribution(distribution),
            "live_telemetry_sample": _telemetry_summary(telemetry),
            "active_incidents": 0,
            "note": "Baseline reset has no generated active incidents before DEMO 2.",
            "tool_calls": [],
        }

    def demo_2_incident_investigation(self) -> dict[str, Any]:
        self.registry.activate_scenario(
            DEMO_DEVICE_ID,
            FailureScenario.NETWORK_TIMEOUT,
            DEFAULT_TEST_TIME,
        )
        published = self.producer.publish_snapshot(DEFAULT_TEST_TIME)
        emitted_events = []
        for event in self.event_bus.topic_events(DEVICE_TELEMETRY_TOPIC):
            emitted_events.extend(self.consumer.process(event))

        alert_events = self.event_bus.topic_events(DEVICE_ALERT_TOPIC)
        incident_events = self.event_bus.topic_events(INCIDENT_CREATED_TOPIC)
        health = self._call(
            "get_device_health",
            {"device_id": DEMO_DEVICE_ID},
            "ai-token",
            "demo-2-health",
        )
        logs = self._call(
            "search_logs",
            {"device_id": DEMO_DEVICE_ID, "severity": "CRITICAL", "limit": 5},
            "ai-token",
            "demo-2-logs",
        )
        telemetry = self._call(
            "get_device_telemetry",
            {"device_id": DEMO_DEVICE_ID, "limit": 1},
            "ai-token",
            "demo-2-telemetry",
        )
        diagnostics = self.agent.handle(f"Why is {DEMO_DEVICE_ID} unhealthy?")

        return {
            "name": "DEMO 2 - Incident investigation",
            "trigger": f"POST /simulator/scenarios/{DEMO_DEVICE_ID}/network-timeout",
            "published_telemetry_events": published,
            "processed_domain_events": len(emitted_events),
            "alert": _first_payload(alert_events),
            "incident": _first_payload(incident_events),
            "device_health": _tool_data(health),
            "logs": _tool_data(logs).get("logs", []),
            "telemetry": _tool_data(telemetry).get("telemetry", []),
            "diagnostic_analysis": {
                "message": diagnostics.message,
                "possible_causes": diagnostics.data.get("diagnostic_report", {}).get(
                    "possible_causes",
                    [],
                ),
                "evidence": diagnostics.evidence,
                "similar_incident": diagnostics.data.get("similar_incidents", [{}])[0],
            },
            "tool_calls": [
                _tool_trace("get_device_health", health),
                _tool_trace("search_logs", logs),
                _tool_trace("get_device_telemetry", telemetry),
                *_agent_trace(
                    diagnostics.trace,
                    [
                        "get_device_status",
                        "get_device_telemetry",
                        "get_device_services",
                        "get_recent_errors",
                        "find_similar_incidents",
                        "run_diagnostic_check",
                        "generate_diagnostic_summary",
                    ],
                ),
            ],
        }

    def demo_3_knowledge_assisted_diagnosis(self) -> dict[str, Any]:
        search = self._call(
            "search_knowledge",
            {"query": "network timeout procedure", "limit": 3},
            "ai-token",
            "demo-3-search",
        )
        procedure = self._call(
            "get_procedure",
            {"procedure_id": "kb-service-restart"},
            "ai-token",
            "demo-3-procedure",
        )
        troubleshooting = self._call(
            "find_troubleshooting_steps",
            {"error_code": "E-NET-TIMEOUT", "device_model": "SIM-ENG-EDGE-1000"},
            "ai-token",
            "demo-3-troubleshooting",
        )
        procedure_data = _tool_data(procedure).get("procedure", {})
        return {
            "name": "DEMO 3 - Knowledge-assisted diagnosis",
            "prompt": "What procedure should I follow for this failure?",
            "answer": {
                "procedure": procedure_data.get("title"),
                "document_id": procedure_data.get("document_id"),
                "fictional_notice": procedure_data.get("fictional_notice"),
                "steps": procedure_data.get("procedure_steps", []),
                "source_citation": "kb-service-restart@1.0-demo#restart-governance",
                "troubleshooting_steps": _tool_data(troubleshooting).get("steps", []),
            },
            "tool_calls": [
                _tool_trace("search_knowledge", search),
                _tool_trace("get_procedure", procedure),
                _tool_trace("find_troubleshooting_steps", troubleshooting),
            ],
        }

    def demo_4_ticket_automation(self) -> dict[str, Any]:
        ticket = self._call(
            "create_ticket",
            {
                "title": "Maintenance ticket for SIM-014 network timeout",
                "description": (
                    "Investigate SIM-014 telemetry-agent network timeout and packet loss."
                ),
                "device_id": DEMO_DEVICE_ID,
                "priority": "CRITICAL",
                "team": "Simulator Operations",
                "diagnostic_evidence": {
                    "error_code": "E-NET-TIMEOUT",
                    "incident": "SIM-014 threshold breach: E-NET-TIMEOUT",
                },
            },
            "operator-token",
            "demo-4-create-ticket",
        )
        ticket_data = _tool_data(ticket).get("ticket", {})
        return {
            "name": "DEMO 4 - Ticket automation",
            "prompt": "Create a maintenance ticket for SIM-014.",
            "ticket_id": ticket_data.get("ticket_id"),
            "ticket": ticket_data,
            "audit_record": self._latest_audit("create_ticket"),
            "tool_calls": [_tool_trace("create_ticket", ticket)],
        }

    def demo_5_high_risk_operation(self) -> dict[str, Any]:
        request = self.agent.handle(f"Restart {DEMO_DEVICE_ID} {DEMO_SERVICE} service.")
        approval_id = request.approval_id
        if approval_id is None:
            raise RuntimeError("Restart request did not create an approval.")

        pending = self.gateway.get_approval("admin-token", approval_id)
        approved = self.gateway.approve_operation("admin-token", approval_id)
        executed = self.agent.handle(
            f"Restart {DEMO_DEVICE_ID} {DEMO_SERVICE} service with approval {approval_id}."
        )
        service_state = self._call(
            "get_service_health",
            {"device_id": DEMO_DEVICE_ID, "service_name": DEMO_SERVICE},
            "ai-token",
            "demo-5-service-health",
        )

        return {
            "name": "DEMO 5 - High-risk operation",
            "prompt": "Restart the affected service.",
            "risk_classification": "HIGH",
            "permission_checked": "devices:operate",
            "approval_required": request.approval_required,
            "pending_approval": _approval_summary(pending),
            "human_approval": _response_summary(approved),
            "execution_result": executed.data,
            "service_state_after_execution": _tool_data(service_state),
            "audit_records": [
                record.model_dump(mode="json")
                for record in self.gateway.audit_log.records
                if record.correlation_id == approval_id or record.tool_name == "restart_service"
            ],
            "tool_calls": [
                *_agent_trace(
                    request.trace,
                    ["get_recent_errors", "get_device_services", "restart_service"],
                ),
                _response_trace("get_approval", pending),
                _response_trace("approve_operation", approved),
                *_agent_trace(executed.trace, ["restart_service"]),
                _tool_trace("get_service_health", service_state),
            ],
        }

    def _call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        auth_token: str,
        idempotency_suffix: str,
        approval_id: UUID | None = None,
    ) -> GatewayToolResponse:
        return self.gateway.call_tool(
            GatewayToolRequest(
                auth_token=auth_token,
                tool_name=tool_name,
                arguments=arguments,
                idempotency_key=_idempotency(idempotency_suffix),
                approval_id=approval_id,
                correlation_id=uuid5(NAMESPACE_URL, f"phase-13:{idempotency_suffix}"),
            )
        )

    def _latest_audit(self, tool_name: str) -> dict[str, Any]:
        for record in reversed(self.gateway.audit_log.records):
            if record.tool_name == tool_name:
                return cast(dict[str, Any], record.model_dump(mode="json"))
        return {}


def _tool_data(response: GatewayToolResponse) -> dict[str, Any]:
    result = response.data.get("tool_result")
    if isinstance(result, dict):
        data = result.get("data")
        if isinstance(data, dict):
            return cast(dict[str, Any], data)
    return response.data


def _tool_trace(tool_name: str, response: GatewayToolResponse) -> dict[str, Any]:
    return {
        "tool": tool_name,
        "ok": response.ok,
        "decision": response.decision.value,
        "correlation_id": str(response.correlation_id),
        "error": response.error,
    }


def _response_trace(name: str, response: GatewayToolResponse) -> dict[str, Any]:
    return {
        "tool": name,
        "ok": response.ok,
        "decision": response.decision.value,
        "correlation_id": str(response.correlation_id),
        "error": response.error,
    }


def _agent_trace(trace: list[Any], tool_names: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "tool": tool_names[index] if index < len(tool_names) else step.tool_name,
            "ok": step.ok,
            "decision": step.decision,
            "approval_id": step.approval_id,
            "error_code": step.error_code,
        }
        for index, step in enumerate(trace)
    ]


def _response_summary(response: GatewayToolResponse) -> dict[str, Any]:
    return {
        "ok": response.ok,
        "decision": response.decision.value,
        "data": response.data,
        "error": response.error,
    }


def _approval_summary(response: GatewayToolResponse) -> dict[str, Any]:
    approval = response.data.get("approval", {})
    if not isinstance(approval, dict):
        return {}
    return {
        "approval_id": approval.get("approval_id"),
        "tool_name": approval.get("tool_name"),
        "risk_level": approval.get("risk_level"),
        "status": approval.get("status"),
        "requester_id": approval.get("requester_id"),
        "expires_at": approval.get("expires_at"),
    }


def _distribution(distribution: Counter[str]) -> dict[str, int]:
    return {
        "HEALTHY": distribution.get("HEALTHY", 0),
        "WARNING": distribution.get("WARNING", 0),
        "CRITICAL": distribution.get("CRITICAL", 0),
        "OFFLINE": distribution.get("OFFLINE", 0),
    }


def _telemetry_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "device_id": payload["device_id"],
        "cpu_percent": payload["cpu_percent"],
        "memory_percent": payload["memory_percent"],
        "temperature_c": payload["temperature_c"],
        "network_latency_ms": payload["network_latency_ms"],
        "packet_loss_percent": payload["packet_loss_percent"],
        "disk_percent": payload["disk_percent"],
        "uptime_seconds": payload["uptime_seconds"],
    }


def _first_payload(events: Sequence[Any]) -> dict[str, Any]:
    if not events:
        return {}
    payload = events[0].payload
    return dict(payload) if isinstance(payload, dict) else {}


def _idempotency(suffix: str) -> str:
    return f"phase-13-{suffix}"


if __name__ == "__main__":
    main()
