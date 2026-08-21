from __future__ import annotations

from dataclasses import replace

from mcp_ops_ai_agent.engineering_rag.models import KnowledgeSearchResult
from mcp_ops_ai_agent.engineering_rag.query_analysis import RagQueryAnalysis
from mcp_ops_ai_agent.tool_discovery.embeddings import tokenize


def rerank_knowledge_results(
    query: str,
    analysis: RagQueryAnalysis,
    results: list[KnowledgeSearchResult],
    *,
    top_k: int,
    max_chunks_per_document: int = 2,
) -> list[KnowledgeSearchResult]:
    reranked = [_with_rerank_score(query, analysis, result) for result in results]
    ordered = sorted(
        reranked,
        key=lambda item: (
            -item.combined_score,
            item.chunk.metadata.stale,
            item.citation_id,
            item.chunk.chunk_id,
        ),
    )
    return _limit_chunks_per_document(
        ordered,
        top_k=top_k,
        max_chunks_per_document=max_chunks_per_document,
    )


def knowledge_rerank_score(
    query: str,
    analysis: RagQueryAnalysis,
    result: KnowledgeSearchResult,
) -> float:
    chunk = result.chunk
    score = result.combined_score * 0.72
    score += _document_type_score(analysis, result)
    score += _entity_score(analysis, result)
    score += _capability_score(analysis, result)
    score += _section_answer_score(query, result)
    if chunk.metadata.stale:
        score -= 0.2
    if chunk.prompt_injection_detected:
        score -= 0.25
    return round(max(0.0, min(1.0, score)), 4)


def _with_rerank_score(
    query: str,
    analysis: RagQueryAnalysis,
    result: KnowledgeSearchResult,
) -> KnowledgeSearchResult:
    score = knowledge_rerank_score(query, analysis, result)
    return replace(
        result,
        combined_score=score,
        reason=_rerank_reason(result.reason, analysis, result),
    )


def _document_type_score(
    analysis: RagQueryAnalysis,
    result: KnowledgeSearchResult,
) -> float:
    if not analysis.likely_document_types:
        return 0.0
    document_type = result.chunk.metadata.document_type
    if document_type in analysis.likely_document_types:
        position = analysis.likely_document_types.index(document_type)
        return round(max(0.04, 0.16 - position * 0.025), 4)
    return -0.04


def _entity_score(analysis: RagQueryAnalysis, result: KnowledgeSearchResult) -> float:
    metadata = result.chunk.metadata
    score = 0.0
    if analysis.service:
        score += 0.12 if metadata.service == analysis.service else -0.1 if metadata.service else 0.0
    if analysis.repository:
        score += (
            0.08
            if metadata.repository == analysis.repository
            else -0.08
            if metadata.repository
            else 0.0
        )
    if analysis.environment:
        score += (
            0.08
            if metadata.environment in {analysis.environment, None}
            else -0.08
            if metadata.environment
            else 0.0
        )
    return round(max(-0.18, min(0.22, score)), 4)


def _capability_score(analysis: RagQueryAnalysis, result: KnowledgeSearchResult) -> float:
    requested = set(analysis.required_capabilities)
    if not requested:
        return 0.0
    available = set(result.chunk.metadata.capability_categories)
    overlap = requested & available
    return round(min(0.14, len(overlap) * 0.045), 4)


def _section_answer_score(query: str, result: KnowledgeSearchResult) -> float:
    query_terms = set(tokenize(query))
    chunk_terms = set(tokenize(result.chunk.text))
    title_terms = set(tokenize(result.chunk.metadata.title))
    score = 0.0
    if query_terms & title_terms:
        score += 0.05
    if query_terms & chunk_terms:
        score += min(0.08, len(query_terms & chunk_terms) * 0.01)
    if _asks_ownership(query_terms) and result.chunk.metadata.document_type == "ownership":
        score += 0.12
    if _asks_runbook(query_terms) and result.chunk.metadata.document_type in {
        "deployment",
        "run_instructions",
    }:
        score += 0.1
    return round(min(score, 0.18), 4)


def _limit_chunks_per_document(
    results: list[KnowledgeSearchResult],
    *,
    top_k: int,
    max_chunks_per_document: int,
) -> list[KnowledgeSearchResult]:
    counts: dict[str, int] = {}
    selected: list[KnowledgeSearchResult] = []
    for result in results:
        count = counts.get(result.citation_id, 0)
        if count >= max_chunks_per_document:
            continue
        selected.append(result)
        counts[result.citation_id] = count + 1
        if len(selected) >= top_k:
            break
    return selected


def _rerank_reason(
    base_reason: str,
    analysis: RagQueryAnalysis,
    result: KnowledgeSearchResult,
) -> str:
    signals: list[str] = []
    if result.chunk.metadata.document_type in analysis.likely_document_types:
        signals.append(f"document_type={result.chunk.metadata.document_type}")
    if analysis.service and result.chunk.metadata.service == analysis.service:
        signals.append(f"service={analysis.service}")
    if analysis.environment and result.chunk.metadata.environment == analysis.environment:
        signals.append(f"environment={analysis.environment}")
    if not signals:
        return base_reason
    return f"{base_reason} Reranked for " + ", ".join(signals[:3]) + "."


def _asks_ownership(query_terms: set[str]) -> bool:
    return bool({"owner", "owns", "team", "escalation"} & query_terms)


def _asks_runbook(query_terms: set[str]) -> bool:
    return bool({"runbook", "procedure", "restart", "deploy", "deployment"} & query_terms)
