from __future__ import annotations

from fastapi.testclient import TestClient
from mcp_ops_mcp_gateway.app import create_app as create_gateway_app
from mcp_ops_simulator.app import create_app as create_simulator_app


def test_mcp_gateway_ready_reports_registry_and_stores() -> None:
    response = TestClient(create_gateway_app()).get("/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["components"]["tool_registry"]["tools"] > 0
    assert payload["components"]["approval_store"]["status"] == "ready"


def test_simulator_ready_reports_registry_and_event_processors() -> None:
    response = TestClient(create_simulator_app()).get("/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["components"]["registry"]["devices"] == 50
    assert payload["components"]["telemetry_consumer"]["status"] == "ready"
