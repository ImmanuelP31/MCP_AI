from mcp_ops_simulator.clock import DEFAULT_TEST_TIME
from mcp_ops_simulator.consumers import TelemetryConsumer
from mcp_ops_simulator.events import (
    DEVICE_ALERT_TOPIC,
    DEVICE_HEALTH_TOPIC,
    DEVICE_TELEMETRY_TOPIC,
    INCIDENT_CREATED_TOPIC,
    InMemoryEventBus,
)
from mcp_ops_simulator.models import DeviceStatus, FailureScenario
from mcp_ops_simulator.producer import TelemetryProducer
from mcp_ops_simulator.registry import DeviceRegistry


def test_telemetry_producer_publishes_one_event_per_device() -> None:
    registry = DeviceRegistry.seeded(base_time=DEFAULT_TEST_TIME)
    event_bus = InMemoryEventBus()
    producer = TelemetryProducer(registry, event_bus)

    published = producer.publish_snapshot(DEFAULT_TEST_TIME)

    assert published == 50
    events = event_bus.topic_events(DEVICE_TELEMETRY_TOPIC)
    assert len(events) == 50
    assert events[13].payload["device_id"] == "SIM-014"


def test_telemetry_consumer_updates_health_and_generates_alert_incident() -> None:
    registry = DeviceRegistry.seeded(base_time=DEFAULT_TEST_TIME)
    registry.activate_scenario("SIM-014", FailureScenario.NETWORK_TIMEOUT, DEFAULT_TEST_TIME)
    event_bus = InMemoryEventBus()
    producer = TelemetryProducer(registry, event_bus)
    consumer = TelemetryConsumer(registry, event_bus)

    producer.publish_snapshot(DEFAULT_TEST_TIME)
    sim_014_event = next(
        event
        for event in event_bus.topic_events(DEVICE_TELEMETRY_TOPIC)
        if event.payload["device_id"] == "SIM-014"
    )
    emitted = consumer.process(sim_014_event)

    device = registry.get_device("SIM-014")
    assert device.status == DeviceStatus.CRITICAL
    assert device.health_score == 18.0
    assert len(emitted) == 3
    assert event_bus.topic_events(DEVICE_HEALTH_TOPIC)
    assert event_bus.topic_events(DEVICE_ALERT_TOPIC)[0].payload["error_code"] == "E-NET-TIMEOUT"
    assert event_bus.topic_events(INCIDENT_CREATED_TOPIC)


def test_consumer_is_idempotent_for_duplicate_events() -> None:
    registry = DeviceRegistry.seeded(base_time=DEFAULT_TEST_TIME)
    event_bus = InMemoryEventBus()
    producer = TelemetryProducer(registry, event_bus)
    consumer = TelemetryConsumer(registry, event_bus)

    producer.publish_snapshot(DEFAULT_TEST_TIME)
    event = event_bus.topic_events(DEVICE_TELEMETRY_TOPIC)[0]

    assert consumer.process(event)
    assert consumer.process(event) == []
