from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from mcp_ops_ai_agent.tool_discovery.embeddings import (
    EmbeddingProvider,
    cosine_similarity,
)
from mcp_ops_ai_agent.tool_discovery.models import ToolDiscoveryFilters, ToolDocument


class ToolIndexUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SemanticMatch:
    tool_name: str
    semantic_score: float


class ToolEmbeddingIndex(Protocol):
    @property
    def backend_name(self) -> str:
        """Human-readable backend name for API/debug output."""

    def search(
        self,
        query: str,
        documents: list[ToolDocument],
        *,
        top_k: int,
        filters: ToolDiscoveryFilters,
    ) -> list[SemanticMatch]:
        """Return semantic/vector matches for candidate tool documents."""


class InMemoryToolEmbeddingIndex:
    def __init__(self, embedding_provider: EmbeddingProvider) -> None:
        self.embedding_provider = embedding_provider

    @property
    def backend_name(self) -> str:
        return "in-memory-hashing"

    def search(
        self,
        query: str,
        documents: list[ToolDocument],
        *,
        top_k: int,
        filters: ToolDiscoveryFilters,
    ) -> list[SemanticMatch]:
        query_embedding = self.embedding_provider.embed(query)
        matches = [
            SemanticMatch(
                tool_name=document.name,
                semantic_score=cosine_similarity(query_embedding, document.embedding),
            )
            for document in _filter_documents(documents, filters)
        ]
        return sorted(matches, key=lambda item: (-item.semantic_score, item.tool_name))[:top_k]


class OpenSearchToolEmbeddingIndex:
    """OpenSearch-compatible boundary for production vector/BM25 storage.

    The local project does not vendor an OpenSearch Python client. This adapter intentionally
    exposes the production boundary while allowing the service to fall back to deterministic local
    retrieval when OpenSearch is unavailable.
    """

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint

    @property
    def backend_name(self) -> str:
        return "opensearch"

    def search(
        self,
        query: str,
        documents: list[ToolDocument],
        *,
        top_k: int,
        filters: ToolDiscoveryFilters,
    ) -> list[SemanticMatch]:
        del query, documents, top_k, filters
        raise ToolIndexUnavailable(
            "OpenSearch tool discovery index is unavailable in this local runtime."
        )


def _filter_documents(
    documents: list[ToolDocument],
    filters: ToolDiscoveryFilters,
) -> list[ToolDocument]:
    filtered = documents
    if filters.allowed_servers:
        filtered = [item for item in filtered if item.server in filters.allowed_servers]
    if filters.allowed_categories:
        filtered = [item for item in filtered if item.category in filters.allowed_categories]
    return filtered
