from __future__ import annotations

from fastapi import FastAPI, HTTPException
from mcp_ops_observability.fastapi import add_observability

from mcp_ops_simulator.clock import DEFAULT_TEST_TIME, DeterministicClock
from mcp_ops_simulator.consumers import TelemetryConsumer
from mcp_ops_simulator.events import DEVICE_TELEMETRY_TOPIC, InMemoryEventBus
from mcp_ops_simulator.models import FailureScenario
from mcp_ops_simulator.producer import TelemetryProducer
from mcp_ops_simulator.registry import DeviceNotFoundError, DeviceRegistry


def create_app(
    *,
    registry: DeviceRegistry | None = None,
    event_bus: InMemoryEventBus | None = None,
    clock: DeterministicClock | None = None,
) -> FastAPI:
    app = FastAPI(
        title="MCP Simulator Gateway",
        version="0.1.0",
        docs_url="/simulator/docs",
        openapi_url="/simulator/openapi.json",
    )
    add_observability(app)
    clock_obj = clock or DeterministicClock(DEFAULT_TEST_TIME)
    registry_obj = registry or DeviceRegistry.seeded(base_time=clock_obj.now())
    event_bus_obj = event_bus or InMemoryEventBus()
    producer_obj = TelemetryProducer(registry_obj, event_bus_obj)
    consumer_obj = TelemetryConsumer(registry_obj, event_bus_obj)
    app.state.clock = clock_obj
    app.state.registry = registry_obj
    app.state.event_bus = event_bus_obj
    app.state.producer = producer_obj
    app.state.consumer = consumer_obj

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/ready", tags=["health"])
    def ready() -> dict[str, object]:
        return {
            "status": "ready",
            "components": {
                "registry": {"status": "ready", "devices": len(registry_obj.list_devices())},
                "event_bus": {"status": "ready"},
                "telemetry_producer": {"status": "ready"},
                "telemetry_consumer": {"status": "ready"},
            },
        }

    @app.get("/simulator/devices", tags=["simulator"])
    def list_devices() -> dict[str, object]:
        devices = registry_obj.list_devices()
        return {"count": len(devices), "devices": [device.as_payload() for device in devices]}

    @app.get("/simulator/devices/{device_id}", tags=["simulator"])
    def get_device(device_id: str) -> dict[str, object]:
        try:
            return registry_obj.get_device(device_id).as_payload()
        except DeviceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="device not found") from exc

    @app.get("/simulator/devices/{device_id}/telemetry", tags=["simulator"])
    def get_telemetry(device_id: str) -> dict[str, object]:
        try:
            return registry_obj.telemetry_for(device_id, clock_obj.now()).as_payload()
        except DeviceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="device not found") from exc

    @app.post("/simulator/scenarios/{device_id}/{scenario}", tags=["simulator"])
    def activate_scenario(device_id: str, scenario: FailureScenario) -> dict[str, object]:
        try:
            device = registry_obj.activate_scenario(device_id, scenario, clock_obj.now())
        except DeviceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="device not found") from exc
        return {"device": device.as_payload(), "scenario": scenario.value}

    @app.delete("/simulator/scenarios/{device_id}", tags=["simulator"])
    def clear_scenario(device_id: str) -> dict[str, object]:
        try:
            device = registry_obj.clear_scenario(device_id, clock_obj.now())
        except DeviceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="device not found") from exc
        return {"device": device.as_payload(), "scenario": None}

    @app.post("/simulator/telemetry/publish", tags=["simulator"])
    def publish_telemetry() -> dict[str, int]:
        published = producer_obj.publish_snapshot(clock_obj.now())
        return {"published": published}

    @app.post("/simulator/telemetry/process", tags=["simulator"])
    def process_telemetry() -> dict[str, int]:
        processed = 0
        emitted = 0
        for event in event_bus_obj.topic_events(DEVICE_TELEMETRY_TOPIC):
            emitted += len(consumer_obj.process(event))
            processed += 1
        return {"processed": processed, "emitted": emitted}

    @app.get("/simulator/events", tags=["simulator"])
    def events() -> dict[str, object]:
        return {
            topic: [event.model_dump(mode="json") for event in topic_events]
            for topic, topic_events in event_bus_obj.all_events().items()
        }

    return app


app = create_app()
