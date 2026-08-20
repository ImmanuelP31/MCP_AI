from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any

import pytest
from mcp_ops_ai_agent.gateway import RemoteMcpGatewayClient, gateway_client_from_settings
from mcp_ops_common.config import Settings
from mcp_ops_mcp_gateway.models import GatewayDecision, GatewayToolRequest


def test_remote_gateway_client_posts_authenticated_tool_request() -> None:
    seen: dict[str, Any] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib callback name.
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            seen["path"] = self.path
            seen["service_token"] = self.headers.get("X-Service-Token")
            seen["correlation_id"] = self.headers.get("X-Correlation-ID")
            seen["body"] = body
            payload = {
                "ok": True,
                "decision": "ALLOWED",
                "correlation_id": body["correlation_id"],
                "data": {"tool_result": {"ok": True, "data": {"device_id": "SIM-014"}}},
                "error": None,
            }
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = GatewayToolRequest(
            auth_token="viewer-token",  # noqa: S106  # nosec B106 - deterministic test token.
            tool_name="get_device",
            arguments={"device_id": "SIM-014"},
            idempotency_key="remote-client-1",
        )
        client = RemoteMcpGatewayClient(
            base_url=f"http://127.0.0.1:{server.server_port}",
            service_token="service-secret",  # noqa: S106  # nosec B106 - deterministic test token.
            timeout_seconds=2,
            transport_retries=0,
        )

        response = client.call_tool(request)
    finally:
        server.shutdown()
        server.server_close()

    assert response.ok
    assert response.decision == GatewayDecision.ALLOWED
    assert seen["path"] == "/api/v1/gateway/tools/call"
    assert seen["service_token"] == "service-secret"  # noqa: S105  # nosec B105
    assert seen["correlation_id"] == str(request.correlation_id)
    assert seen["body"]["tool_name"] == "get_device"


def test_remote_gateway_client_returns_structured_unavailable_error() -> None:
    request = GatewayToolRequest(
        auth_token="viewer-token",  # noqa: S106  # nosec B106 - deterministic test token.
        tool_name="get_device",
        arguments={"device_id": "SIM-014"},
        idempotency_key="remote-client-unavailable",
    )
    client = RemoteMcpGatewayClient(
        base_url="http://127.0.0.1:1",
        service_token="service-secret",  # noqa: S106  # nosec B106 - deterministic test token.
        timeout_seconds=1,
        transport_retries=0,
    )

    response = client.call_tool(request)

    assert not response.ok
    assert response.error is not None
    assert response.error["code"] == "gateway_unavailable"


def test_gateway_client_factory_forbids_in_process_mode_in_production() -> None:
    settings = Settings(environment="production", mcp_gateway_client_mode="in_process")

    with pytest.raises(RuntimeError, match="In-process MCP gateway client"):
        gateway_client_from_settings(settings)


def test_gateway_client_factory_auto_uses_remote_for_production() -> None:
    settings = Settings(
        environment="production",
        mcp_gateway_client_mode="auto",
        mcp_gateway_url="http://gateway.internal:8002",
    )

    client = gateway_client_from_settings(settings)

    assert isinstance(client, RemoteMcpGatewayClient)
