from __future__ import annotations

import json
from http.client import HTTPConnection, HTTPException, HTTPSConnection
from typing import Protocol
from urllib.parse import urlparse
from uuid import UUID

from mcp_ops_common.config import Settings, get_settings
from mcp_ops_mcp_gateway.models import GatewayDecision, GatewayToolRequest, GatewayToolResponse
from mcp_ops_mcp_gateway.service import McpGateway


class GatewayClient(Protocol):
    def call_tool(self, request: GatewayToolRequest) -> GatewayToolResponse:
        """Execute a governed MCP tool request through the MCP gateway."""


class McpGatewayClient:
    def __init__(self, gateway: McpGateway | None = None) -> None:
        self.gateway = gateway or McpGateway()

    def call_tool(self, request: GatewayToolRequest) -> GatewayToolResponse:
        return self.gateway.call_tool(request)


class RemoteMcpGatewayClient:
    def __init__(
        self,
        *,
        base_url: str,
        service_token: str,
        timeout_seconds: int = 10,
        transport_retries: int = 1,
    ) -> None:
        parsed = urlparse(base_url.rstrip("/"))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("MCP gateway URL must be an HTTP(S) URL.")
        self.scheme = parsed.scheme
        self.host = parsed.hostname
        self.port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self.path_prefix = parsed.path.rstrip("/")
        self.service_token = service_token
        self.timeout_seconds = timeout_seconds
        self.transport_retries = max(0, transport_retries)

    def call_tool(self, request: GatewayToolRequest) -> GatewayToolResponse:
        payload = json.dumps(request.model_dump(mode="json")).encode("utf-8")
        attempts = self.transport_retries + 1
        last_error: BaseException | None = None
        for _ in range(attempts):
            try:
                return self._post_json(request, payload)
            except (OSError, HTTPException, TimeoutError) as exc:
                last_error = exc
        return _transport_failure_response(request, last_error)

    def _post_json(self, request: GatewayToolRequest, payload: bytes) -> GatewayToolResponse:
        connection_cls = HTTPSConnection if self.scheme == "https" else HTTPConnection
        connection = connection_cls(self.host, self.port, timeout=self.timeout_seconds)
        try:
            connection.request(
                "POST",
                f"{self.path_prefix}/api/v1/gateway/tools/call",
                body=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Service-Token": self.service_token,
                    "X-Correlation-ID": str(request.correlation_id),
                },
            )
            response = connection.getresponse()
            raw = response.read()
        finally:
            connection.close()
        if response.status >= 500:
            raise ConnectionError(f"MCP gateway returned HTTP {response.status}.")
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return _transport_failure_response(request, RuntimeError("Malformed gateway response."))
        if response.status >= 400:
            return _error_response_from_body(request, body, response.status)
        return _gateway_response_from_json(body)


def gateway_client_from_settings(settings: Settings | None = None) -> GatewayClient:
    current = settings or get_settings()
    mode = current.mcp_gateway_client_mode.lower()
    if mode == "auto":
        mode = "remote" if current.environment in {"staging", "production"} else "in_process"
    if mode == "in_process":
        if current.environment == "production":
            raise RuntimeError("In-process MCP gateway client is not allowed in production.")
        return McpGatewayClient()
    if mode != "remote":
        raise ValueError("MCP_GATEWAY_CLIENT_MODE must be 'auto', 'remote', or 'in_process'.")
    return RemoteMcpGatewayClient(
        base_url=current.mcp_gateway_url,
        service_token=current.service_auth_shared_secret,
        timeout_seconds=current.mcp_gateway_timeout_seconds,
        transport_retries=current.mcp_gateway_transport_retries,
    )


def _gateway_response_from_json(payload: object) -> GatewayToolResponse:
    if not isinstance(payload, dict):
        raise ValueError("Gateway response must be an object.")
    coerced = dict(payload)
    if isinstance(coerced.get("decision"), str):
        coerced["decision"] = GatewayDecision(coerced["decision"])
    if isinstance(coerced.get("correlation_id"), str):
        coerced["correlation_id"] = UUID(coerced["correlation_id"])
    return GatewayToolResponse.model_validate(coerced)


def _error_response_from_body(
    request: GatewayToolRequest,
    payload: object,
    status_code: int,
) -> GatewayToolResponse:
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        error = payload["error"]
        code = str(error.get("code") or f"http_{status_code}")
        message = str(error.get("message") or "MCP gateway request failed.")
    else:
        code = f"http_{status_code}"
        message = "MCP gateway request failed."
    return GatewayToolResponse(
        ok=False,
        decision=GatewayDecision.DENIED,
        correlation_id=request.correlation_id,
        data={"tool_name": request.tool_name},
        error={"code": code, "message": message},
    )


def _transport_failure_response(
    request: GatewayToolRequest,
    exc: BaseException | None,
) -> GatewayToolResponse:
    reason = exc.__class__.__name__ if exc else "unknown"
    return GatewayToolResponse(
        ok=False,
        decision=GatewayDecision.DENIED,
        correlation_id=request.correlation_id,
        data={"tool_name": request.tool_name},
        error={
            "code": "gateway_unavailable",
            "message": f"MCP gateway unavailable: {reason}",
        },
    )
