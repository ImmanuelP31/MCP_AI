from __future__ import annotations

import json
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPSConnection
from typing import Any, Protocol
from urllib.parse import quote, urlparse

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
    """OpenSearch-backed tool index with deterministic local fallback on failure."""

    def __init__(self, endpoint: str, *, index_name: str = "mcp-tools") -> None:
        self.endpoint = endpoint
        self.index_name = index_name

    @property
    def backend_name(self) -> str:
        return "opensearch"

    def index_documents(self, documents: list[ToolDocument]) -> None:
        for document in documents:
            payload = {
                "name": document.name,
                "description": document.description,
                "server": document.server,
                "category": document.category,
                "risk_level": document.risk_level,
                "required_permission": document.required_permission,
                "required_roles": list(document.required_roles),
                "tags": list(document.tags),
                "executable": document.executable,
                "enabled": document.enabled,
                "discovery_text": document.discovery_text,
                "embedding": list(document.embedding),
            }
            self._request(
                "PUT",
                f"/{quote(self.index_name)}/_doc/{quote(document.name)}",
                payload,
            )

    def search(
        self,
        query: str,
        documents: list[ToolDocument],
        *,
        top_k: int,
        filters: ToolDiscoveryFilters,
    ) -> list[SemanticMatch]:
        del documents
        filter_clauses: list[dict[str, object]] = []
        if filters.allowed_servers:
            filter_clauses.append({"terms": {"server.keyword": sorted(filters.allowed_servers)}})
        if filters.allowed_categories:
            filter_clauses.append(
                {"terms": {"category.keyword": sorted(filters.allowed_categories)}}
            )
        body: dict[str, object] = {
            "size": top_k,
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "name^4",
                                    "tags^3",
                                    "description^2",
                                    "category",
                                    "server",
                                    "discovery_text",
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
        matches: list[SemanticMatch] = []
        for hit in hits:
            source = hit.get("_source")
            if not isinstance(source, dict):
                continue
            name = source.get("name")
            if not isinstance(name, str):
                continue
            score = round(float(hit.get("_score") or 0.0) / max_score, 4)
            matches.append(SemanticMatch(tool_name=name, semantic_score=score))
        return matches

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        parsed = urlparse(self.endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ToolIndexUnavailable("OpenSearch endpoint must be an HTTP(S) URL.")
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
            raise ToolIndexUnavailable(
                f"OpenSearch tool index request failed: {exc.__class__.__name__}."
            ) from exc
        finally:
            connection.close()
        if response.status >= 400:
            raise ToolIndexUnavailable(f"OpenSearch tool index returned HTTP {response.status}.")
        decoded = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(decoded, dict):
            raise ToolIndexUnavailable("OpenSearch tool index response must be an object.")
        return decoded


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
