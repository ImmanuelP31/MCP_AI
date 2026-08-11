from collections.abc import Callable
from typing import Any, cast

from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from mcp_ops_simulator.app import create_app
from mcp_ops_simulator.events import (
    DEVICE_ALERT_TOPIC,
    DEVICE_TELEMETRY_TOPIC,
    INCIDENT_CREATED_TOPIC,
)
from mcp_ops_simulator.models import FailureScenario


def test_scenario_controller_activates_known_failure_and_processes_events() -> None:
    app = create_app()

    activate_scenario = _route(app, "/simulator/scenarios/{device_id}/{scenario}", "POST")
    get_telemetry = _route(app, "/simulator/devices/{device_id}/telemetry", "GET")
    publish_telemetry = _route(app, "/simulator/telemetry/publish", "POST")
    process_telemetry = _route(app, "/simulator/telemetry/process", "POST")
    events_endpoint = _route(app, "/simulator/events", "GET")

    scenario_response = activate_scenario("SIM-014", FailureScenario.NETWORK_TIMEOUT)
    assert scenario_response["scenario"] == "network-timeout"

    telemetry = get_telemetry("SIM-014")
    assert telemetry["network_latency_ms"] == 5000.0

    assert publish_telemetry() == {"published": 50}

    process_response = process_telemetry()
    assert process_response["processed"] == 50

    events = events_endpoint()
    assert len(events[DEVICE_TELEMETRY_TOPIC]) == 50
    assert events[DEVICE_ALERT_TOPIC]
    assert events[INCIDENT_CREATED_TOPIC]


def test_scenario_controller_returns_404_for_unknown_device() -> None:
    app = create_app()
    activate_scenario = _route(app, "/simulator/scenarios/{device_id}/{scenario}", "POST")

    try:
        activate_scenario("SIM-999", FailureScenario.NETWORK_TIMEOUT)
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("Expected unknown simulator device to return 404")


def _route(app: FastAPI, path: str, method: str) -> Callable[..., dict[str, Any]]:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and route.methods is not None:
            if method not in route.methods:
                continue
            return cast(Callable[..., dict[str, Any]], route.endpoint)
    raise AssertionError(f"Route {method} {path} not found")
