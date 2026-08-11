from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp_ops_auth.rbac import Permission, Role, has_permission
from mcp_ops_policy.tool_registry import ToolMetadata
from pydantic import BaseModel, ValidationError

from mcp_ops_mcp.errors import (
    McpDomainError,
    PermissionDenied,
    ServiceUnavailable,
    ToolDisabled,
    ToolTimeout,
)
from mcp_ops_mcp.schemas import AuthorizedInput, StructuredError, StructuredOutput

Handler = Callable[[Any], StructuredOutput]


@dataclass(frozen=True)
class ToolDefinition:
    metadata: ToolMetadata
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Handler

    def to_mcp_tool(self) -> types.Tool:
        return types.Tool(
            name=self.metadata.tool_name,
            description=self.metadata.description,
            input_schema=self.input_model.model_json_schema(),
            output_schema=self.output_model.model_json_schema(),
        )


class McpToolDispatcher:
    def __init__(
        self,
        tools: Sequence[ToolDefinition],
        *,
        disabled_tools: set[str] | None = None,
        unavailable_tools: set[str] | None = None,
        timeout_tools: set[str] | None = None,
    ) -> None:
        self._tools = {tool.metadata.tool_name: tool for tool in tools}
        self._disabled_tools = disabled_tools or set()
        self._unavailable_tools = unavailable_tools or set()
        self._timeout_tools = timeout_tools or set()

    def list_tools(self) -> list[types.Tool]:
        return [tool.to_mcp_tool() for tool in self._tools.values()]

    def call_tool(self, tool_name: str, arguments: dict[str, Any] | None) -> types.CallToolResult:
        try:
            definition = self._tool_definition(tool_name)
            parsed = definition.input_model.model_validate(arguments or {})
            self._authorize(definition, parsed)
            self._check_availability(definition.metadata.tool_name)
            output = definition.handler(parsed)
            return _success_result(output)
        except ValidationError as exc:
            return _error_result("validation_error", exc.errors(include_url=False))
        except McpDomainError as exc:
            return _error_result(exc.code, exc.message)

    def validate_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None,
    ) -> types.CallToolResult:
        try:
            definition = self._tool_definition(tool_name)
            parsed = definition.input_model.model_validate(arguments or {})
            self._authorize(definition, parsed)
            self._check_availability(definition.metadata.tool_name)
            return _success_result(StructuredOutput(ok=True, data={"validated": True}))
        except ValidationError as exc:
            return _error_result("validation_error", exc.errors(include_url=False))
        except McpDomainError as exc:
            return _error_result(exc.code, exc.message)

    def _tool_definition(self, tool_name: str) -> ToolDefinition:
        try:
            return self._tools[tool_name]
        except KeyError as exc:
            raise ToolDisabled(f"Tool {tool_name} is not registered.") from exc

    def _authorize(self, definition: ToolDefinition, parsed: BaseModel) -> None:
        if definition.metadata.tool_name in self._disabled_tools or not definition.metadata.enabled:
            raise ToolDisabled(f"Tool {definition.metadata.tool_name} is disabled.")
        if not isinstance(parsed, AuthorizedInput):
            raise PermissionDenied("Tool input does not include gateway actor context.")
        role = Role(parsed.actor_role)
        permission = Permission(definition.metadata.required_permission)
        if not has_permission(role, permission):
            raise PermissionDenied(
                f"Role {role.value} lacks permission {definition.metadata.required_permission}."
            )

    def _check_availability(self, tool_name: str) -> None:
        if tool_name in self._unavailable_tools:
            raise ServiceUnavailable(f"Backing service for {tool_name} is unavailable.")
        if tool_name in self._timeout_tools:
            raise ToolTimeout(f"Tool {tool_name} exceeded its execution timeout.")


def build_lowlevel_server(name: str, dispatcher: McpToolDispatcher) -> Server:
    async def on_list_tools(_ctx: object, _params: object) -> types.ListToolsResult:
        return types.ListToolsResult(tools=dispatcher.list_tools())

    async def on_call_tool(
        _ctx: object,
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult:
        return dispatcher.call_tool(params.name, params.arguments)

    return Server(name, on_list_tools=on_list_tools, on_call_tool=on_call_tool)


def _success_result(output: StructuredOutput) -> types.CallToolResult:
    payload = output.model_dump(mode="json")
    return types.CallToolResult(
        content=[types.TextContent(text=json.dumps(payload, sort_keys=True))],
        structured_content=payload,
        is_error=False,
    )


def _error_result(code: str, details: object) -> types.CallToolResult:
    payload = StructuredError(error={"code": code, "message": str(details)}).model_dump(mode="json")
    return types.CallToolResult(
        content=[types.TextContent(text=json.dumps(payload, sort_keys=True))],
        structured_content=payload,
        is_error=True,
    )
