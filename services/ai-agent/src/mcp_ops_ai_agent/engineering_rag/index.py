from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from mcp_ops_ai_agent.engineering_rag.models import KnowledgeChunk, KnowledgeFilters
from mcp_ops_ai_agent.tool_discovery.embeddings import (
    EmbeddingProvider,
    cosine_similarity,
)


class KnowledgeIndexUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SemanticKnowledgeMatch:
    chunk_id: str
    semantic_score: float


class KnowledgeIndex(Protocol):
    @property
    def backend_name(self) -> str:
        """Human-readable backend name for API/debug output."""

    def search(
        self,
        query: str,
        chunks: list[KnowledgeChunk],
        *,
        top_k: int,
        filters: KnowledgeFilters,
    ) -> list[SemanticKnowledgeMatch]:
        """Return vector matches for candidate engineering knowledge chunks."""


class InMemoryKnowledgeIndex:
    def __init__(self, embedding_provider: EmbeddingProvider) -> None:
        self.embedding_provider = embedding_provider

    @property
    def backend_name(self) -> str:
        return "in-memory-hashing"

    def search(
        self,
        query: str,
        chunks: list[KnowledgeChunk],
        *,
        top_k: int,
        filters: KnowledgeFilters,
    ) -> list[SemanticKnowledgeMatch]:
        query_embedding = self.embedding_provider.embed(query)
        matches = [
            SemanticKnowledgeMatch(
                chunk_id=chunk.chunk_id,
                semantic_score=cosine_similarity(query_embedding, chunk.embedding),
            )
            for chunk in _filter_chunks(chunks, filters)
        ]
        return sorted(matches, key=lambda item: (-item.semantic_score, item.chunk_id))[:top_k]


class OpenSearchKnowledgeIndex:
    """OpenSearch boundary for production RAG storage.

    The local deterministic suite uses the in-memory fallback. A real deployment can replace this
    adapter with OpenSearch k-NN/BM25 queries without changing API or planner contracts.
    """

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint

    @property
    def backend_name(self) -> str:
        return "opensearch"

    def search(
        self,
        query: str,
        chunks: list[KnowledgeChunk],
        *,
        top_k: int,
        filters: KnowledgeFilters,
    ) -> list[SemanticKnowledgeMatch]:
        del query, chunks, top_k, filters
        raise KnowledgeIndexUnavailable(
            "OpenSearch engineering knowledge index is unavailable in this local runtime."
        )


def _filter_chunks(chunks: list[KnowledgeChunk], filters: KnowledgeFilters) -> list[KnowledgeChunk]:
    filtered = chunks
    if filters.document_type:
        filtered = [
            item
            for item in filtered
            if item.metadata.document_type == filters.document_type
        ]
    if filters.service:
        filtered = [item for item in filtered if item.metadata.service == filters.service]
    if filters.repository:
        filtered = [item for item in filtered if item.metadata.repository == filters.repository]
    if filters.environment:
        filtered = [
            item
            for item in filtered
            if item.metadata.environment in {filters.environment, None}
        ]
    if not filters.include_stale:
        filtered = [item for item in filtered if not item.metadata.stale]
    return filtered
