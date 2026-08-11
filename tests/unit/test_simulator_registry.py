from datetime import timedelta

from mcp_ops_simulator.clock import DEFAULT_TEST_TIME
from mcp_ops_simulator.models import DeviceStatus, FailureScenario, ServiceState
from mcp_ops_simulator.registry import DeviceRegistry


def test_seeded_registry_has_50_deterministic_devices() -> None:
    registry = DeviceRegistry.seeded(base_time=DEFAULT_TEST_TIME)

    devices = registry.list_devices()

    assert len(devices) == 50
    assert devices[0].device_id == "SIM-001"
    assert devices[-1].device_id == "SIM-050"
    assert devices[13].serial_number == "SN-MCP-00014"


def test_network_timeout_scenario_changes_telemetry_and_service_state() -> None:
    registry = DeviceRegistry.seeded(base_time=DEFAULT_TEST_TIME)

    registry.activate_scenario("SIM-014", FailureScenario.NETWORK_TIMEOUT, DEFAULT_TEST_TIME)
    telemetry = registry.telemetry_for("SIM-014", DEFAULT_TEST_TIME)

    assert telemetry.network_latency_ms == 5000.0
    assert telemetry.packet_loss_percent == 100.0
    assert telemetry.service_states["telemetry-agent"] == ServiceState.DEGRADED


def test_telemetry_delay_uses_deterministic_lagged_timestamp() -> None:
    registry = DeviceRegistry.seeded(base_time=DEFAULT_TEST_TIME)

    registry.activate_scenario("SIM-014", FailureScenario.TELEMETRY_DELAY, DEFAULT_TEST_TIME)
    telemetry = registry.telemetry_for("SIM-014", DEFAULT_TEST_TIME)

    assert telemetry.delayed
    assert telemetry.timestamp == DEFAULT_TEST_TIME - timedelta(minutes=7)


def test_clear_scenario_restores_healthy_device_state() -> None:
    registry = DeviceRegistry.seeded(base_time=DEFAULT_TEST_TIME)

    registry.activate_scenario("SIM-014", FailureScenario.SERVICE_CRASH, DEFAULT_TEST_TIME)
    registry.clear_scenario("SIM-014", DEFAULT_TEST_TIME)
    device = registry.get_device("SIM-014")

    assert device.active_scenario is None
    assert device.status == DeviceStatus.HEALTHY
    assert all(service.state == ServiceState.RUNNING for service in device.services.values())
