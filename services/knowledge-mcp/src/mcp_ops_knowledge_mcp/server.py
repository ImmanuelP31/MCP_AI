from __future__ import annotations

from mcp.server.lowlevel import Server
from mcp_ops_mcp.dispatcher import McpToolDispatcher, ToolDefinition, build_lowlevel_server
from mcp_ops_mcp.schemas import (
    KnowledgeDocumentInput,
    KnowledgeSearchInput,
    ProcedureInput,
    StructuredOutput,
    TroubleshootingInput,
)
from mcp_ops_mcp.services import KnowledgeDomainService
from mcp_ops_policy.tool_registry import TOOL_REGISTRY


def create_dispatcher(
    service: KnowledgeDomainService | None = None,
    *,
    disabled_tools: set[str] | None = None,
    unavailable_tools: set[str] | None = None,
    timeout_tools: set[str] | None = None,
) -> McpToolDispatcher:
    service = service or KnowledgeDomainService()
    tools = [
        ToolDefinition(
            TOOL_REGISTRY["search_knowledge"],
            KnowledgeSearchInput,
            StructuredOutput,
            lambda model: service.search(model.query, model.limit),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_document"],
            KnowledgeDocumentInput,
            StructuredOutput,
            lambda model: service.document(model.document_id),
        ),
        ToolDefinition(
            TOOL_REGISTRY["get_procedure"],
            ProcedureInput,
            StructuredOutput,
            lambda model: service.procedure(model.procedure_id),
        ),
        ToolDefinition(
            TOOL_REGISTRY["find_troubleshooting_steps"],
            TroubleshootingInput,
            StructuredOutput,
            lambda model: service.troubleshooting(model.error_code, model.device_model),
        ),
        ToolDefinition(
            TOOL_REGISTRY["search_configuration_guides"],
            KnowledgeSearchInput,
            StructuredOutput,
            lambda model: service.configuration_guides(model.query, model.limit),
        ),
    ]
    return McpToolDispatcher(
        tools,
        disabled_tools=disabled_tools,
        unavailable_tools=unavailable_tools,
        timeout_tools=timeout_tools,
    )


def create_server(dispatcher: McpToolDispatcher | None = None) -> Server:
    return build_lowlevel_server("knowledge-mcp", dispatcher or create_dispatcher())


server = create_server()

