from __future__ import annotations

from datetime import datetime, timedelta

from mcp_ops_simulator.ids import deterministic_uuid, telemetry_id
from mcp_ops_simulator.models import (
    DeviceService,
    DeviceStatus,
    DeviceTelemetry,
    FailureScenario,
    ServiceState,
    SimulatedDevice,
)


class DeviceNotFoundError(ValueError):
    pass


class DeviceRegistry:
    def __init__(self, devices: list[SimulatedDevice]) -> None:
        self._devices = {device.device_id: device for device in devices}

    @classmethod
    def seeded(cls, *, base_time: datetime) -> DeviceRegistry:
        return cls(_seed_devices(base_time))

    def list_devices(self) -> list[SimulatedDevice]:
        return [self._devices[device_id] for device_id in sorted(self._devices)]

    def get_device(self, device_id: str) -> SimulatedDevice:
        try:
            return self._devices[device_id]
        except KeyError as exc:
            raise DeviceNotFoundError(device_id) from exc

    def activate_scenario(
        self,
        device_id: str,
        scenario: FailureScenario,
        now: datetime,
    ) -> SimulatedDevice:
        device = self.get_device(device_id)
        device.active_scenario = scenario
        device.last_seen = now
        _apply_scenario_to_services(device, scenario)
        return device

    def clear_scenario(self, device_id: str, now: datetime) -> SimulatedDevice:
        device = self.get_device(device_id)
        device.active_scenario = None
        device.status = DeviceStatus.HEALTHY
        device.health_score = 96.0
        device.last_seen = now
        for service in device.services.values():
            service.state = ServiceState.RUNNING
        return device

    def update_health(
        self,
        device_id: str,
        status: DeviceStatus,
        health_score: float,
        now: datetime,
    ) -> None:
        device = self.get_device(device_id)
        device.status = status
        device.health_score = health_score
        device.last_seen = now

    def telemetry_for(self, device_id: str, now: datetime) -> DeviceTelemetry:
        device = self.get_device(device_id)
        index = int(device.device_id.split("-")[1])
        timestamp = now
        delayed = False
        if device.active_scenario == FailureScenario.TELEMETRY_DELAY:
            timestamp = now - timedelta(minutes=7)
            delayed = True

        telemetry = _base_telemetry(device, index, timestamp, delayed=delayed)
        if device.active_scenario is None:
            return telemetry
        return _apply_scenario_to_telemetry(telemetry, device.active_scenario)

    def telemetry_snapshot(self, now: datetime) -> list[DeviceTelemetry]:
        return [self.telemetry_for(device.device_id, now) for device in self.list_devices()]


def _seed_devices(base_time: datetime) -> list[SimulatedDevice]:
    service_names = ["telemetry-agent", "control-plane", "sensor-ingestor", "diagnostic-runner"]
    models = ["SIM-X100", "SIM-X200", "SIM-RUGGED"]
    sites = ["Bangalore Lab", "Pune Integration", "Austin HIL", "Munich Validation"]
    devices: list[SimulatedDevice] = []
    for number in range(1, 51):
        device_id = f"SIM-{number:03d}"
        boot_time = base_time - timedelta(days=7, hours=number)
        services = {
            service_name: DeviceService(
                name=service_name,
                state=ServiceState.RUNNING,
                version=f"v{2 + index}.{number % 10}.{index}",
                last_restart_at=base_time - timedelta(hours=number + index),
            )
            for index, service_name in enumerate(service_names)
        }
        devices.append(
            SimulatedDevice(
                internal_id=deterministic_uuid(f"device:{device_id}"),
                device_id=device_id,
                serial_number=f"SN-MCP-{number:05d}",
                model=models[number % len(models)],
                location=f"Rack {((number - 1) % 10) + 1}, Slot {((number - 1) % 5) + 1}",
                site=sites[number % len(sites)],
                firmware_version=f"2026.{(number % 4) + 1}.{(number % 9) + 1}",
                status=DeviceStatus.HEALTHY,
                health_score=96.0,
                last_seen=base_time - timedelta(minutes=number % 17),
                boot_time=boot_time,
                services=services,
            )
        )
    return devices


def _base_telemetry(
    device: SimulatedDevice,
    index: int,
    timestamp: datetime,
    *,
    delayed: bool,
) -> DeviceTelemetry:
    service_states = {name: service.state for name, service in device.services.items()}
    return DeviceTelemetry(
        telemetry_id=telemetry_id(device.device_id, timestamp),
        device_id=device.device_id,
        timestamp=timestamp,
        cpu_percent=float(25 + (index * 3) % 45),
        memory_percent=float(35 + (index * 5) % 35),
        temperature_c=float(38 + index % 18),
        network_latency_ms=float(25 + (index * 7) % 100),
        packet_loss_percent=float(index % 5) / 10.0,
        disk_percent=float(45 + index % 30),
        uptime_seconds=max(0, int((timestamp - device.boot_time).total_seconds())),
        service_states=service_states,
        delayed=delayed,
    )


def _apply_scenario_to_services(device: SimulatedDevice, scenario: FailureScenario) -> None:
    if scenario in {
        FailureScenario.SERVICE_CRASH,
        FailureScenario.SENSOR_INITIALIZATION_FAILURE,
    }:
        device.services["sensor-ingestor"].state = ServiceState.CRASHED
    elif scenario == FailureScenario.NETWORK_TIMEOUT:
        device.services["telemetry-agent"].state = ServiceState.DEGRADED
    else:
        for service in device.services.values():
            service.state = ServiceState.RUNNING


def _apply_scenario_to_telemetry(
    telemetry: DeviceTelemetry, scenario: FailureScenario
) -> DeviceTelemetry:
    values = telemetry.as_payload()
    service_states = dict(telemetry.service_states)
    if scenario == FailureScenario.SERVICE_CRASH:
        service_states["sensor-ingestor"] = ServiceState.CRASHED
    elif scenario == FailureScenario.CPU_SATURATION:
        values["cpu_percent"] = 98.4
    elif scenario == FailureScenario.MEMORY_PRESSURE:
        values["memory_percent"] = 94.2
    elif scenario == FailureScenario.PACKET_LOSS:
        values["packet_loss_percent"] = 18.5
    elif scenario == FailureScenario.NETWORK_TIMEOUT:
        values["network_latency_ms"] = 5000.0
        values["packet_loss_percent"] = 100.0
        service_states["telemetry-agent"] = ServiceState.DEGRADED
    elif scenario == FailureScenario.SENSOR_INITIALIZATION_FAILURE:
        service_states["sensor-ingestor"] = ServiceState.CRASHED
        values["temperature_c"] = 82.0
    elif scenario == FailureScenario.DISK_CAPACITY_WARNING:
        values["disk_percent"] = 91.0

    return DeviceTelemetry(
        telemetry_id=telemetry.telemetry_id,
        device_id=telemetry.device_id,
        timestamp=telemetry.timestamp,
        cpu_percent=float(values["cpu_percent"]),
        memory_percent=float(values["memory_percent"]),
        temperature_c=float(values["temperature_c"]),
        network_latency_ms=float(values["network_latency_ms"]),
        packet_loss_percent=float(values["packet_loss_percent"]),
        disk_percent=float(values["disk_percent"]),
        uptime_seconds=telemetry.uptime_seconds,
        service_states=service_states,
        delayed=telemetry.delayed,
    )
