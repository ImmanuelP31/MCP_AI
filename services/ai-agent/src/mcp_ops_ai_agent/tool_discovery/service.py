from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

from mcp_ops_auth.rbac import ROLE_PERMISSIONS, Permission
from mcp_ops_common.config import Settings, get_settings
from mcp_ops_device_mcp.server import create_dispatcher as create_device_dispatcher
from mcp_ops_diagnostics_mcp.server import create_dispatcher as create_diagnostics_dispatcher
from mcp_ops_knowledge_mcp.server import create_dispatcher as create_knowledge_dispatcher
from mcp_ops_observability.metrics import record_tool_discovery_request
from mcp_ops_policy.tool_registry import TOOL_REGISTRY, ToolMetadata
from mcp_ops_repository_mcp.server import create_dispatcher as create_repository_dispatcher
from mcp_ops_ticket_mcp.server import create_dispatcher as create_ticket_dispatcher

from mcp_ops_ai_agent.tool_discovery.embeddings import (
    EmbeddingProvider,
    embedding_provider_from_settings,
)
from mcp_ops_ai_agent.tool_discovery.index import (
    InMemoryToolEmbeddingIndex,
    OpenSearchToolEmbeddingIndex,
    ToolEmbeddingIndex,
    ToolIndexUnavailable,
)
from mcp_ops_ai_agent.tool_discovery.models import (
    ToolDiscoveryFilters,
    ToolDiscoveryRequest,
    ToolDiscoveryResponse,
    ToolDiscoveryResult,
    ToolDocument,
)
from mcp_ops_ai_agent.tool_discovery.retrieval import combined_score, explanation


class ToolMetadataError(ValueError):
    pass


class ToolDiscoveryService:
    def __init__(
        self,
        *,
        registry: Mapping[str, ToolMetadata] | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        index: ToolEmbeddingIndex | None = None,
        input_schemas: Mapping[str, dict[str, Any]] | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.registry = TOOL_REGISTRY if registry is None else registry
        self.embedding_provider = embedding_provider or embedding_provider_from_settings(
            self.settings
        )
        self.index = index or _index_from_settings(self.settings, self.embedding_provider)
        self.input_schemas = dict(input_schemas or default_input_schemas())
        self.documents = [
            self._document_from_metadata(name, metadata)
            for name, metadata in sorted(self.registry.items())
        ]
        _try_index_documents(self.index, self.documents)

    def retrieve(
        self,
        query: str,
        *,
        role: str = "ENGINEER",
        top_k: int = 8,
        minimum_score: float = 0.0,
        allowed_servers: set[str] | None = None,
        allowed_categories: set[str] | None = None,
    ) -> ToolDiscoveryResponse:
        request = ToolDiscoveryRequest(
            query=query,
            role=role,
            top_k=_top_k(top_k),
            minimum_score=max(0.0, minimum_score),
            filters=ToolDiscoveryFilters(
                allowed_servers=frozenset(allowed_servers or set()),
                allowed_categories=frozenset(allowed_categories or set()),
            ),
        )
        started = time.perf_counter()
        backend = self.index.backend_name
        try:
            results = self._retrieve_with_index(request, self.index, backend)
        except ToolIndexUnavailable:
            fallback = InMemoryToolEmbeddingIndex(self.embedding_provider)
            backend = f"fallback:{fallback.backend_name}"
            results = self._retrieve_with_index(request, fallback, backend)
        latency = time.perf_counter() - started
        record_tool_discovery_request(
            role=request.role,
            index_backend=backend,
            result_count=len(results.ranked_tools),
            latency_seconds=latency,
        )
        return results

    def safe_tools_for_planner(
        self,
        query: str,
        *,
        role: str,
        top_k: int = 12,
    ) -> list[ToolDocument]:
        response = self.retrieve(query, role=role, top_k=top_k)
        return [result.tool for result in response.ranked_tools]

    def _retrieve_with_index(
        self,
        request: ToolDiscoveryRequest,
        index: ToolEmbeddingIndex,
        backend: str,
    ) -> ToolDiscoveryResponse:
        candidate_k = max(request.top_k * 4, request.top_k + 12)
        semantic_matches = index.search(
            request.query,
            self.documents,
            top_k=candidate_k,
            filters=request.filters,
        )
        semantic_by_name = {match.tool_name: match.semantic_score for match in semantic_matches}
        document_by_name = {document.name: document for document in self.documents}
        ranked: list[ToolDiscoveryResult] = []
        unauthorized = 0
        for tool_name, semantic_score in semantic_by_name.items():
            document = document_by_name[tool_name]
            lexical, score = combined_score(request.query, document, semantic_score)
            if score < request.minimum_score:
                continue
            if not _role_authorized(request.role, document):
                unauthorized += 1
                continue
            ranked.append(
                ToolDiscoveryResult(
                    tool=document,
                    semantic_score=round(semantic_score, 4),
                    lexical_score=lexical,
                    combined_score=score,
                    authorization_status="authorized",
                    explanation=explanation(request.query, document),
                )
            )
        ranked = sorted(ranked, key=lambda item: (-item.combined_score, item.tool.name))
        return ToolDiscoveryResponse(
            query=request.query,
            role=request.role,
            ranked_tools=ranked[: request.top_k],
            filtered_out_unauthorized=unauthorized,
            index_backend=backend,
        )

    def _document_from_metadata(self, name: str, metadata: ToolMetadata) -> ToolDocument:
        if name != metadata.tool_name:
            raise ToolMetadataError(f"Registry key {name} does not match tool metadata name.")
        for field_name in ("tool_name", "description", "server", "category", "required_permission"):
            value = getattr(metadata, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ToolMetadataError(f"Tool {name} has malformed {field_name}.")
        input_schema = self.input_schemas.get(metadata.tool_name) or _default_input_schema(metadata)
        required_roles = tuple(metadata.required_roles or _roles_for_permission(metadata))
        document = ToolDocument(
            name=metadata.tool_name,
            description=metadata.description,
            server=metadata.server,
            category=metadata.category,
            risk_level=metadata.risk_level.value,
            required_permission=metadata.required_permission,
            required_roles=required_roles,
            input_schema=input_schema,
            tags=tuple(metadata.tags),
            executable=metadata.executable,
            enabled=metadata.enabled,
        )
        return ToolDocument(
            **{
                **document.as_payload(),
                "required_roles": document.required_roles,
                "tags": document.tags,
                "embedding": self.embedding_provider.embed(document.discovery_text),
            }
        )


def default_input_schemas() -> dict[str, dict[str, Any]]:
    schemas: dict[str, dict[str, Any]] = {}
    for dispatcher in (
        create_device_dispatcher(),
        create_diagnostics_dispatcher(),
        create_knowledge_dispatcher(),
        create_repository_dispatcher(),
        create_ticket_dispatcher(),
    ):
        for tool in dispatcher.list_tools():
            schemas[tool.name] = dict(tool.input_schema)
    return schemas


def _default_input_schema(metadata: ToolMetadata) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "query": {
            "type": "string",
            "description": f"Natural-language selector for {metadata.tool_name}.",
        }
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
    }


def _roles_for_permission(metadata: ToolMetadata) -> list[str]:
    try:
        permission = Permission(metadata.required_permission)
    except ValueError:
        return []
    return [
        role.value
        for role, permissions in ROLE_PERMISSIONS.items()
        if permission in permissions
    ]


def _role_authorized(role: str, document: ToolDocument) -> bool:
    if not document.enabled:
        return False
    if not document.required_roles:
        return True
    return role.upper() in {item.upper() for item in document.required_roles}


def _top_k(value: int) -> int:
    return min(max(value, 1), 50)


def _index_from_settings(
    settings: Settings,
    embedding_provider: EmbeddingProvider,
) -> ToolEmbeddingIndex:
    if settings.tool_discovery_index_backend.lower() == "opensearch":
        return OpenSearchToolEmbeddingIndex(
            settings.opensearch_url,
            index_name=settings.opensearch_tool_index,
        )
    return InMemoryToolEmbeddingIndex(embedding_provider)


def _try_index_documents(index: ToolEmbeddingIndex, documents: list[ToolDocument]) -> None:
    indexer = getattr(index, "index_documents", None)
    if not callable(indexer):
        return
    try:
        indexer(documents)
    except ToolIndexUnavailable:
        return
