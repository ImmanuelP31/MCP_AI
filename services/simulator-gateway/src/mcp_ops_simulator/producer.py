from datetime import datetime

from mcp_ops_simulator.events import DEVICE_TELEMETRY_TOPIC, EventPublisher, telemetry_event
from mcp_ops_simulator.registry import DeviceRegistry


class TelemetryProducer:
    def __init__(self, registry: DeviceRegistry, publisher: EventPublisher) -> None:
        self.registry = registry
        self.publisher = publisher

    def publish_snapshot(self, now: datetime) -> int:
        count = 0
        for telemetry in self.registry.telemetry_snapshot(now):
            self.publisher.publish(DEVICE_TELEMETRY_TOPIC, telemetry_event(telemetry))
            count += 1
        return count
