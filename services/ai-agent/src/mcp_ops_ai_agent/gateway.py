from __future__ import annotations

from typing import Protocol

from mcp_ops_mcp_gateway.models import GatewayToolRequest, GatewayToolResponse
from mcp_ops_mcp_gateway.service import McpGateway


class GatewayClient(Protocol):
    def call_tool(self, request: GatewayToolRequest) -> GatewayToolResponse:
        """Execute a governed MCP tool request through the MCP gateway."""


class McpGatewayClient:
    def __init__(self, gateway: McpGateway | None = None) -> None:
        self.gateway = gateway or McpGateway()

    def call_tool(self, request: GatewayToolRequest) -> GatewayToolResponse:
        return self.gateway.call_tool(request)
