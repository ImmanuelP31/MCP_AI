from __future__ import annotations

import json
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPSConnection
from typing import Any, Protocol
from urllib.parse import quote, urlparse

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
    """OpenSearch-backed engineering knowledge index with local fallback on failure."""

    def __init__(self, endpoint: str, *, index_name: str = "engineering-knowledge") -> None:
        self.endpoint = endpoint
        self.index_name = index_name

    @property
    def backend_name(self) -> str:
        return "opensearch"

    def index_chunks(self, chunks: list[KnowledgeChunk]) -> None:
        for chunk in chunks:
            payload: dict[str, object] = {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.metadata.document_id,
                "title": chunk.metadata.title,
                "document_type": chunk.metadata.document_type,
                "service": chunk.metadata.service or "",
                "repository": chunk.metadata.repository or "",
                "environment": chunk.metadata.environment or "",
                "owner": chunk.metadata.owner or "",
                "version": chunk.metadata.version,
                "source": chunk.metadata.source,
                "updated_at": chunk.metadata.updated_at.isoformat(),
                "stale": chunk.metadata.stale,
                "capability_categories": list(chunk.metadata.capability_categories),
                "text": chunk.text,
                "search_text": chunk.search_text,
                "embedding": list(chunk.embedding),
            }
            self._request(
                "PUT",
                f"/{quote(self.index_name)}/_doc/{quote(chunk.chunk_id)}",
                payload,
            )

    def search(
        self,
        query: str,
        chunks: list[KnowledgeChunk],
        *,
        top_k: int,
        filters: KnowledgeFilters,
    ) -> list[SemanticKnowledgeMatch]:
        del chunks
        filter_clauses: list[dict[str, object]] = []
        if filters.document_type:
            filter_clauses.append({"term": {"document_type.keyword": filters.document_type}})
        if filters.service:
            filter_clauses.append({"term": {"service.keyword": filters.service}})
        if filters.repository:
            filter_clauses.append({"term": {"repository.keyword": filters.repository}})
        if filters.environment:
            filter_clauses.append({"terms": {"environment.keyword": [filters.environment, ""]}})
        if not filters.include_stale:
            filter_clauses.append({"term": {"stale": False}})
        body: dict[str, object] = {
            "size": top_k,
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "document_id^4",
                                    "title^3",
                                    "repository^2",
                                    "service^2",
                                    "document_type",
                                    "capability_categories",
                                    "search_text",
                                    "text",
                                ],
                            }
                        }
                    ],
                    "filter": filter_clauses,
                }
            },
        }
        response = self._request("POST", f"/{quote(self.index_name)}/_search", body)
        hits = _hits(response)
        if not hits:
            return []
        max_score = max(float(hit.get("_score") or 0.0) for hit in hits) or 1.0
        matches: list[SemanticKnowledgeMatch] = []
        for hit in hits:
            source = hit.get("_source")
            if not isinstance(source, dict):
                continue
            chunk_id = source.get("chunk_id")
            if not isinstance(chunk_id, str):
                continue
            score = round(float(hit.get("_score") or 0.0) / max_score, 4)
            matches.append(SemanticKnowledgeMatch(chunk_id=chunk_id, semantic_score=score))
        return matches

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        parsed = urlparse(self.endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise KnowledgeIndexUnavailable("OpenSearch endpoint must be an HTTP(S) URL.")
        connection_cls = HTTPSConnection if parsed.scheme == "https" else HTTPConnection
        payload = None if body is None else json.dumps(body).encode("utf-8")
        connection = connection_cls(
            parsed.hostname,
            parsed.port or _default_port(parsed.scheme),
            timeout=3,
        )
        try:
            connection.request(
                method,
                path,
                body=payload,
                headers={"Content-Type": "application/json"} if payload is not None else {},
            )
            response = connection.getresponse()
            raw = response.read(5_000_000)
        except OSError as exc:
            raise KnowledgeIndexUnavailable(
                f"OpenSearch knowledge index request failed: {exc.__class__.__name__}."
            ) from exc
        finally:
            connection.close()
        if response.status >= 400:
            raise KnowledgeIndexUnavailable(
                f"OpenSearch knowledge index returned HTTP {response.status}."
            )
        decoded = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(decoded, dict):
            raise KnowledgeIndexUnavailable(
                "OpenSearch knowledge index response must be an object."
            )
        return decoded


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


def _hits(response: dict[str, Any]) -> list[dict[str, Any]]:
    hits = response.get("hits")
    if not isinstance(hits, dict):
        return []
    raw_hits = hits.get("hits")
    if not isinstance(raw_hits, list):
        return []
    return [hit for hit in raw_hits if isinstance(hit, dict)]


def _default_port(scheme: str) -> int:
    return 443 if scheme == "https" else 80
