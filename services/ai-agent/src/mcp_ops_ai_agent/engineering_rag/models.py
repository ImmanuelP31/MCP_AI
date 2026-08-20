from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class KnowledgeSearchMode(StrEnum):
    BM25 = "bm25"
    VECTOR = "vector"
    HYBRID = "hybrid"


@dataclass(frozen=True, slots=True)
class EngineeringDocumentMetadata:
    document_id: str
    title: str
    document_type: str
    service: str | None = None
    repository: str | None = None
    environment: str | None = None
    owner: str | None = None
    version: str = "1.0"
    source: str = "synthetic-engineering-corpus"
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    stale: bool = False
    capability_categories: tuple[str, ...] = ()

    def as_payload(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "document_type": self.document_type,
            "service": self.service,
            "repository": self.repository,
            "environment": self.environment,
            "owner": self.owner,
            "version": self.version,
            "source": self.source,
            "updated_at": self.updated_at.isoformat(),
            "stale": self.stale,
            "capability_categories": list(self.capability_categories),
        }


@dataclass(frozen=True, slots=True)
class EngineeringDocument:
    metadata: EngineeringDocumentMetadata
    content: str
    format: str = "markdown"


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    chunk_id: str
    metadata: EngineeringDocumentMetadata
    text: str
    embedding: tuple[float, ...] = field(default_factory=tuple)
    prompt_injection_detected: bool = False

    @property
    def search_text(self) -> str:
        parts = [
            self.metadata.document_id,
            self.metadata.title,
            self.metadata.document_type,
            self.metadata.service or "",
            self.metadata.repository or "",
            self.metadata.environment or "",
            self.metadata.owner or "",
            self.metadata.version,
            " ".join(self.metadata.capability_categories),
            self.text,
        ]
        return " ".join(parts)


@dataclass(frozen=True, slots=True)
class KnowledgeFilters:
    document_type: str | None = None
    service: str | None = None
    repository: str | None = None
    environment: str | None = None
    include_stale: bool = False


@dataclass(frozen=True, slots=True)
class EngineeringKnowledgeSearchRequest:
    query: str
    top_k: int = 5
    mode: KnowledgeSearchMode = KnowledgeSearchMode.HYBRID
    minimum_score: float = 0.0
    filters: KnowledgeFilters = field(default_factory=KnowledgeFilters)


@dataclass(frozen=True, slots=True)
class KnowledgeSearchResult:
    chunk: KnowledgeChunk
    lexical_score: float
    semantic_score: float
    combined_score: float
    citation_id: str
    reason: str
    conflict_group: str | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk.chunk_id,
            "citation_id": self.citation_id,
            "document": self.chunk.metadata.as_payload(),
            "text": self.chunk.text[:900],
            "lexical_score": self.lexical_score,
            "semantic_score": self.semantic_score,
            "combined_score": self.combined_score,
            "reason": self.reason,
            "classification": "UNTRUSTED_RETRIEVED_EVIDENCE",
            "prompt_injection_detected": self.chunk.prompt_injection_detected,
            "conflict_group": self.conflict_group,
        }


@dataclass(frozen=True, slots=True)
class EngineeringKnowledgeSearchResponse:
    query: str
    mode: str
    index_backend: str
    results: list[KnowledgeSearchResult]

    def as_payload(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "mode": self.mode,
            "index_backend": self.index_backend,
            "results": [result.as_payload() for result in self.results],
        }


@dataclass(frozen=True, slots=True)
class RagBenchmarkCase:
    case_id: str
    query: str
    expected_document_ids: tuple[str, ...]
    filters: KnowledgeFilters = field(default_factory=KnowledgeFilters)


@dataclass(frozen=True, slots=True)
class RagEvaluationResult:
    cases: int
    mode: str
    recall_at_k: float
    precision_at_k: float
    mrr: float

    def as_payload(self) -> dict[str, float | int | str]:
        return {
            "cases": self.cases,
            "mode": self.mode,
            "recall_at_k": self.recall_at_k,
            "precision_at_k": self.precision_at_k,
            "mrr": self.mrr,
        }
