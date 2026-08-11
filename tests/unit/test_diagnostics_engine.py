from __future__ import annotations

from typing import Any

import pytest
from mcp_ops_mcp.diagnostics import RuleBasedDiagnosticsEngine
from mcp_ops_mcp.services import DiagnosticsDomainService
from mcp_ops_simulator.clock import DEFAULT_TEST_TIME
from mcp_ops_simulator.models import FailureScenario
from mcp_ops_simulator.registry import DeviceRegistry

EXPECTED_CAUSES = {
    FailureScenario.SERVICE_CRASH: "service failure candidate",
    FailureScenario.CPU_SATURATION: "CPU saturation candidate",
    FailureScenario.MEMORY_PRESSURE: "memory pressure candidate",
    FailureScenario.PACKET_LOSS: "network communication issue",
    FailureScenario.NETWORK_TIMEOUT: "network communication issue",
    FailureScenario.SENSOR_INITIALIZATION_FAILURE: "sensor initialization failure",
    FailureScenario.TELEMETRY_DELAY: "telemetry delay",
    FailureScenario.DISK_CAPACITY_WARNING: "disk capacity warning",
}


@pytest.mark.parametrize("scenario,expected_cause", sorted(EXPECTED_CAUSES.items()))
def test_rule_based_diagnostics_cover_every_failure_scenario(
    scenario: FailureScenario,
    expected_cause: str,
) -> None:
    registry = DeviceRegistry.seeded(base_time=DEFAULT_TEST_TIME)
    registry.activate_scenario("SIM-014", scenario, DEFAULT_TEST_TIME)
    device = registry.get_device("SIM-014")
    telemetry = registry.telemetry_for("SIM-014", DEFAULT_TEST_TIME)
    engine = RuleBasedDiagnosticsEngine()

    report = engine.diagnose(
        device,
        telemetry,
        _errors_for_scenario(scenario),
        _historical_incidents(),
    )

    assert report.diagnostic_id
    assert report.device_id == "SIM-014"
    assert report.timestamp == telemetry.timestamp
    assert report.severity in {"INFO", "WARNING", "CRITICAL"}
    assert expected_cause in report.possible_causes
    assert report.observations
    assert any(item.matched for item in report.evidence)
    assert report.recommended_actions
    assert 0.0 < report.confidence <= 0.95
    assert report.related_incidents
    assert [event.event_type for event in report.timeline]
    assert "telemetry_collected" in [event.event_type for event in report.timeline]


def test_diagnostics_service_summary_returns_structured_report() -> None:
    registry = DeviceRegistry.seeded(base_time=DEFAULT_TEST_TIME)
    registry.activate_scenario(
        "SIM-014",
        FailureScenario.NETWORK_TIMEOUT,
        DEFAULT_TEST_TIME,
    )
    service = DiagnosticsDomainService()
    service.device_service.registry = registry

    result = service.summary("SIM-014")
    report = result.data["diagnostic_report"]

    assert result.ok
    assert report["device_id"] == "SIM-014"
    assert "network communication issue" in report["possible_causes"]
    assert report["timeline"]
    assert report["evidence"]
    assert report["related_incidents"][0]["similarity"] > 0.5
    assert "network" in report["related_incidents"][0]["matched_signals"]


def _errors_for_scenario(scenario: FailureScenario) -> list[dict[str, Any]]:
    common = {
        "timestamp": DEFAULT_TEST_TIME.isoformat(),
        "device_id": "SIM-014",
        "service": "sensor-ingestor",
        "severity": "ERROR",
        "correlation_id": "corr-test",
    }
    mapping = {
        FailureScenario.SERVICE_CRASH: {
            "message": "sensor-ingestor crash detected by supervisor.",
            "error_code": "E-SERVICE-CRASH",
        },
        FailureScenario.CPU_SATURATION: {
            "message": "Process response latency high while CPU is saturated.",
            "error_code": "E-CPU-LATENCY",
        },
        FailureScenario.MEMORY_PRESSURE: {
            "message": "Memory pressure warning during telemetry publish.",
            "error_code": "E-MEM-PRESSURE",
        },
        FailureScenario.PACKET_LOSS: {
            "message": "Network timeout while packet loss exceeded threshold.",
            "error_code": "E-NET-TIMEOUT",
        },
        FailureScenario.NETWORK_TIMEOUT: {
            "message": "Network timeout while publishing telemetry.",
            "error_code": "E-NET-TIMEOUT",
        },
        FailureScenario.SENSOR_INITIALIZATION_FAILURE: {
            "message": "Sensor initialization failed and service crash followed.",
            "error_code": "E-SENSOR-INIT",
        },
        FailureScenario.TELEMETRY_DELAY: {
            "message": "Telemetry delay exceeded expected scheduler interval.",
            "error_code": "E-TELEMETRY-DELAY",
        },
        FailureScenario.DISK_CAPACITY_WARNING: {
            "message": "Disk capacity warning threshold exceeded.",
            "error_code": "E-DISK-CAPACITY",
        },
    }
    return [{**common, **mapping[scenario]}]


def _historical_incidents() -> list[dict[str, Any]]:
    return [
        {
            "incident_id": "INC-NET-001",
            "title": "Packet loss with network timeout errors",
            "signals": ["packet_loss", "network_timeout_error", "degraded_service"],
        },
        {
            "incident_id": "INC-CPU-001",
            "title": "CPU saturation with high response latency",
            "signals": ["cpu_percent", "high_latency"],
        },
        {
            "incident_id": "INC-SVC-001",
            "title": "Service crash with supervisor crash log",
            "signals": ["crashed_service", "crash_log"],
        },
        {
            "incident_id": "INC-SENSOR-001",
            "title": "Sensor initialization failure",
            "signals": ["sensor_initialization_error", "crashed_service"],
        },
        {
            "incident_id": "INC-DISK-001",
            "title": "Disk capacity warning",
            "signals": ["disk_percent"],
        },
        {
            "incident_id": "INC-DELAY-001",
            "title": "Telemetry delay",
            "signals": ["telemetry_delay"],
        },
        {
            "incident_id": "INC-MEM-001",
            "title": "Memory pressure",
            "signals": ["memory_percent"],
        },
    ]
