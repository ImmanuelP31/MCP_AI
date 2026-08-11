from __future__ import annotations

from mcp.server.lowlevel import Server
from mcp_ops_mcp.dispatcher import McpToolDispatcher, ToolDefinition, build_lowlevel_server
from mcp_ops_mcp.schemas import (
    AssignTicketInput,
    CreateTicketInput,
    OpenTicketsInput,
    SearchTicketsInput,
    StructuredOutput,
    TicketIdInput,
    UpdateTicketInput,
)
from mcp_ops_mcp.services import TicketDomainService
from mcp_ops_policy.tool_registry import TOOL_REGISTRY


def create_dispatcher(
    service: TicketDomainService | None = None,
    *,
    disabled_tools: set[str] | None = None,
    unavailable_tools: set[str] | None = None,
    timeout_tools: set[str] | None = None,
) -> McpToolDispatcher:
    service = service or TicketDomainService()
    tools = [
        ToolDefinition(
            TOOL_REGISTRY["create_ticket"],
            CreateTicketInput,
            StructuredOutput,
            lambda model: service.create(model.model_dump(), model.actor_role),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_ticket"],
            TicketIdInput,
            StructuredOutput,
            lambda model: service.get(model.ticket_id),
        ),
        ToolDefinition(
            TOOL_REGISTRY["update_ticket"],
            UpdateTicketInput,
            StructuredOutput,
            lambda model: service.update(
                model.ticket_id,
                model.status,
                model.priority,
                model.description,
            ),
        ),
        ToolDefinition(
            TOOL_REGISTRY["assign_ticket"],
            AssignTicketInput,
            StructuredOutput,
            lambda model: service.assign(model.ticket_id, model.assignee),
        ),
        ToolDefinition(
            TOOL_REGISTRY["search_tickets"],
            SearchTicketsInput,
            StructuredOutput,
            lambda model: service.search(
                model.query,
                model.status,
                model.device_id,
                model.limit,
            ),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_open_tickets"],
            OpenTicketsInput,
            StructuredOutput,
            lambda model: service.open_tickets(model.limit),
        ),
    ]
    return McpToolDispatcher(
        tools,
        disabled_tools=disabled_tools,
        unavailable_tools=unavailable_tools,
        timeout_tools=timeout_tools,
    )


def create_server(dispatcher: McpToolDispatcher | None = None) -> Server:
    return build_lowlevel_server("ticket-mcp", dispatcher or create_dispatcher())


server = create_server()

