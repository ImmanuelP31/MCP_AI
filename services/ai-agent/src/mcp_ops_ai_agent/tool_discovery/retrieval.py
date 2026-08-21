from __future__ import annotations

import math
from collections import Counter

from mcp_ops_ai_agent.tool_discovery.embeddings import expanded_tokens, tokenize
from mcp_ops_ai_agent.tool_discovery.intent import (
    RetrievalIntent,
    capability_penalty,
    capability_score,
    document_capabilities,
)
from mcp_ops_ai_agent.tool_discovery.models import ToolDocument


def lexical_score(query: str, document: ToolDocument) -> float:
    query_terms = Counter(expanded_tokens(query))
    if not query_terms:
        return 0.0
    document_terms = Counter(expanded_tokens(document.discovery_text))
    if not document_terms:
        return 0.0

    score = 0.0
    document_length = sum(document_terms.values())
    average_length = 18.0
    k1 = 1.2
    b = 0.75
    for term, query_weight in query_terms.items():
        frequency = document_terms[term]
        if frequency == 0:
            continue
        idf = 1.0 + math.log(1.0 + query_weight)
        denominator = frequency + k1 * (1.0 - b + b * document_length / average_length)
        score += idf * ((frequency * (k1 + 1.0)) / denominator)
    return round(min(1.0, score / max(1.0, len(query_terms) * 0.9)), 4)


def metadata_score(query: str, document: ToolDocument) -> float:
    terms = set(tokenize(query))
    if not terms:
        return 0.0
    tags = {token for tag in document.tags for token in tokenize(tag)}
    name_terms = set(tokenize(document.name))
    category_terms = set(tokenize(document.category))
    score = 0.0
    if terms & name_terms:
        score += 0.12
    if terms & tags:
        score += 0.1
    if terms & category_terms:
        score += 0.06
    return round(min(score, 0.2), 4)


def combined_score(
    query: str,
    document: ToolDocument,
    semantic_score: float,
    *,
    semantic_weight: float = 0.5,
    lexical_weight: float = 0.4,
    metadata_weight: float = 1.0,
    intent: RetrievalIntent | None = None,
) -> tuple[float, float]:
    lexical = lexical_score(query, document)
    metadata = metadata_score(query, document)
    capability = capability_score(intent, document) if intent else 0.0
    combined = (
        semantic_score * semantic_weight
        + lexical * lexical_weight
        + metadata * metadata_weight
        + capability
    )
    if intent is not None:
        combined -= capability_penalty(intent, document)
    elif not document.executable:
        combined -= 0.01
    return lexical, round(max(0.0, min(1.0, combined)), 4)


def explanation(
    query: str,
    document: ToolDocument,
    intent: RetrievalIntent | None = None,
) -> str:
    query_terms = set(tokenize(query))
    matches = sorted(query_terms & set(expanded_tokens(document.discovery_text)))
    if intent is not None:
        overlap = sorted(intent.requested_capabilities & document_capabilities(document))
        if overlap:
            return "Matched requested capabilities: " + ", ".join(overlap[:5]) + "."
    if matches:
        return "Matched request terms: " + ", ".join(matches[:5]) + "."
    if document.category in query.lower():
        return f"Matched requested engineering category {document.category}."
    return "Selected by semantic similarity to the tool description and tags."
