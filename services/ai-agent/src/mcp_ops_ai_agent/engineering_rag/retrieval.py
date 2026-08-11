from __future__ import annotations

import math
import re
from collections import Counter

from mcp_ops_ai_agent.engineering_rag.models import KnowledgeChunk
from mcp_ops_ai_agent.tool_discovery.embeddings import expanded_tokens, tokenize


def lexical_score(query: str, chunk: KnowledgeChunk) -> float:
    query_terms = Counter(expanded_tokens(query))
    document_terms = Counter(expanded_tokens(chunk.search_text))
    if not query_terms or not document_terms:
        return 0.0
    score = 0.0
    document_length = sum(document_terms.values())
    average_length = 80.0
    k1 = 1.2
    b = 0.75
    for term, weight in query_terms.items():
        frequency = document_terms[term]
        if frequency == 0:
            continue
        idf = 1.0 + math.log(1.0 + weight)
        denominator = frequency + k1 * (1.0 - b + b * document_length / average_length)
        score += idf * ((frequency * (k1 + 1.0)) / denominator)
    return round(min(1.0, score / max(1.0, len(query_terms) * 0.75)), 4)


def metadata_score(query: str, chunk: KnowledgeChunk) -> float:
    terms = set(tokenize(query))
    metadata_terms = set(
        tokenize(
            " ".join(
                [
                    chunk.metadata.document_id,
                    chunk.metadata.title,
                    chunk.metadata.document_type,
                    chunk.metadata.service or "",
                    chunk.metadata.repository or "",
                    chunk.metadata.environment or "",
                    chunk.metadata.owner or "",
                ]
            )
        )
    )
    if not terms:
        return 0.0
    overlap = terms & metadata_terms
    return round(min(0.18, len(overlap) * 0.045), 4)


def combined_score(query: str, chunk: KnowledgeChunk, semantic_score: float) -> tuple[float, float]:
    lexical = lexical_score(query, chunk)
    metadata = metadata_score(query, chunk)
    combined = semantic_score * 0.42 + lexical * 0.45 + metadata
    requested_resources = set(re.findall(r"[a-z0-9]+-[a-z0-9]+", query.lower()))
    chunk_resource = chunk.metadata.repository or chunk.metadata.service
    if requested_resources and chunk_resource and chunk_resource not in requested_resources:
        combined -= 0.24
    if chunk.metadata.environment and chunk.metadata.environment in query.lower():
        combined += 0.08
    if chunk.metadata.stale:
        combined -= 0.18
    if chunk.prompt_injection_detected:
        combined -= 0.2
    return lexical, round(max(0.0, min(1.0, combined)), 4)


def explanation(query: str, chunk: KnowledgeChunk) -> str:
    matches = sorted(set(tokenize(query)) & set(expanded_tokens(chunk.search_text)))
    if matches:
        return "Matched engineering context: " + ", ".join(matches[:6]) + "."
    if chunk.metadata.service:
        return f"Relevant to service {chunk.metadata.service}."
    return "Selected by semantic similarity to engineering documentation."
