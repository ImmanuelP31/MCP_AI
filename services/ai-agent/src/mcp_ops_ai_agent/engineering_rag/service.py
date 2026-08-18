from __future__ import annotations

import time
from collections.abc import Iterable

from mcp_ops_common.config import Settings, get_settings
from mcp_ops_observability.metrics import record_rag_query

from mcp_ops_ai_agent.engineering_rag.corpus import synthetic_engineering_corpus
from mcp_ops_ai_agent.engineering_rag.index import (
    InMemoryKnowledgeIndex,
    KnowledgeIndex,
    KnowledgeIndexUnavailable,
    OpenSearchKnowledgeIndex,
)
from mcp_ops_ai_agent.engineering_rag.ingestion import ingest_document
from mcp_ops_ai_agent.engineering_rag.models import (
    EngineeringDocument,
    EngineeringKnowledgeSearchRequest,
    EngineeringKnowledgeSearchResponse,
    KnowledgeChunk,
    KnowledgeSearchMode,
    KnowledgeSearchResult,
)
from mcp_ops_ai_agent.engineering_rag.repo_docs import repository_engineering_documents
from mcp_ops_ai_agent.engineering_rag.retrieval import combined_score, explanation, lexical_score
from mcp_ops_ai_agent.tool_discovery.embeddings import (
    EmbeddingProvider,
    embedding_provider_from_settings,
)


class EngineeringRagService:
    def __init__(
        self,
        *,
        documents: Iterable[EngineeringDocument] | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        index: KnowledgeIndex | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.embedding_provider = embedding_provider or embedding_provider_from_settings(
            self.settings
        )
        self.index = index or _index_from_settings(self.settings, self.embedding_provider)
        source_documents = list(documents) if documents is not None else self._default_documents()
        self.chunks = [
            chunk
            for document in source_documents
            for chunk in ingest_document(document, embedding_provider=self.embedding_provider)
        ]
        _try_index_chunks(self.index, self.chunks)

    def search(
        self,
        request: EngineeringKnowledgeSearchRequest,
    ) -> EngineeringKnowledgeSearchResponse:
        started = time.perf_counter()
        top_k = min(max(request.top_k, 1), 20)
        backend = self.index.backend_name
        try:
            results = self._search_with_index(request, self.index, backend, top_k=top_k)
        except KnowledgeIndexUnavailable:
            fallback = InMemoryKnowledgeIndex(self.embedding_provider)
            backend = f"fallback:{fallback.backend_name}"
            results = self._search_with_index(request, fallback, backend, top_k=top_k)
        latency = time.perf_counter() - started
        record_rag_query(
            mode=request.mode.value,
            index_backend=backend,
            result_count=len(results.results),
            latency_seconds=latency,
        )
        return results

    def _search_with_index(
        self,
        request: EngineeringKnowledgeSearchRequest,
        index: KnowledgeIndex,
        backend: str,
        *,
        top_k: int,
    ) -> EngineeringKnowledgeSearchResponse:
        candidate_k = max(top_k * 5, top_k + 20)
        semantic_matches = index.search(
            request.query,
            self.chunks,
            top_k=candidate_k,
            filters=request.filters,
        )
        semantic_by_chunk = {match.chunk_id: match.semantic_score for match in semantic_matches}
        chunk_by_id = {chunk.chunk_id: chunk for chunk in self.chunks}
        ranked: list[KnowledgeSearchResult] = []
        candidate_ids = set(semantic_by_chunk)
        if request.mode in {KnowledgeSearchMode.BM25, KnowledgeSearchMode.HYBRID}:
            candidate_ids.update(
                chunk.chunk_id
                for chunk in self._filtered_chunks(request)
                if lexical_score(request.query, chunk) > 0
            )
        for chunk_id in candidate_ids:
            chunk = chunk_by_id[chunk_id]
            semantic = semantic_by_chunk.get(chunk_id, 0.0)
            lexical, hybrid = combined_score(request.query, chunk, semantic)
            if request.mode == KnowledgeSearchMode.BM25:
                score = lexical
            elif request.mode == KnowledgeSearchMode.VECTOR:
                score = semantic
            else:
                score = hybrid
            if score < request.minimum_score:
                continue
            ranked.append(
                KnowledgeSearchResult(
                    chunk=chunk,
                    lexical_score=round(lexical, 4),
                    semantic_score=round(semantic, 4),
                    combined_score=round(score, 4),
                    citation_id=chunk.metadata.document_id,
                    reason=explanation(request.query, chunk),
                    conflict_group=_conflict_group(chunk),
                )
            )
        ranked = sorted(
            ranked,
            key=lambda item: (-item.combined_score, item.chunk.metadata.stale, item.citation_id),
        )
        ranked = _dedupe_by_citation(ranked)
        return EngineeringKnowledgeSearchResponse(
            query=request.query,
            mode=request.mode.value,
            index_backend=backend,
            results=ranked[:top_k],
        )

    def _filtered_chunks(self, request: EngineeringKnowledgeSearchRequest) -> list[KnowledgeChunk]:
        return [
            chunk
            for chunk in self.chunks
            if (
                not request.filters.document_type
                or chunk.metadata.document_type == request.filters.document_type
            )
            and (not request.filters.service or chunk.metadata.service == request.filters.service)
            and (
                not request.filters.repository
                or chunk.metadata.repository == request.filters.repository
            )
            and (
                not request.filters.environment
                or chunk.metadata.environment in {request.filters.environment, None}
            )
            and (request.filters.include_stale or not chunk.metadata.stale)
        ]

    def _default_documents(self) -> list[EngineeringDocument]:
        documents = synthetic_engineering_corpus()
        if self.settings.rag_include_repository_docs:
            documents = [*documents, *repository_engineering_documents()]
        return documents


def _conflict_group(chunk: KnowledgeChunk) -> str | None:
    if chunk.metadata.document_type in {"deployment", "environment_policy"}:
        parts = [
            chunk.metadata.document_type,
            chunk.metadata.service or "*",
            chunk.metadata.repository or "*",
            chunk.metadata.environment or "*",
        ]
        return ":".join(parts)
    return None


def _dedupe_by_citation(results: list[KnowledgeSearchResult]) -> list[KnowledgeSearchResult]:
    selected: dict[str, KnowledgeSearchResult] = {}
    for result in results:
        existing = selected.get(result.citation_id)
        if existing is None or result.combined_score > existing.combined_score:
            selected[result.citation_id] = result
    return sorted(
        selected.values(),
        key=lambda item: (-item.combined_score, item.chunk.metadata.stale, item.citation_id),
    )


def _index_from_settings(
    settings: Settings,
    embedding_provider: EmbeddingProvider,
) -> KnowledgeIndex:
    if settings.knowledge_index_backend.lower() == "opensearch":
        return OpenSearchKnowledgeIndex(
            settings.opensearch_url,
            index_name=settings.opensearch_knowledge_index,
        )
    return InMemoryKnowledgeIndex(embedding_provider)


def _try_index_chunks(index: KnowledgeIndex, chunks: list[KnowledgeChunk]) -> None:
    indexer = getattr(index, "index_chunks", None)
    if not callable(indexer):
        return
    try:
        indexer(chunks)
    except KnowledgeIndexUnavailable:
        return
