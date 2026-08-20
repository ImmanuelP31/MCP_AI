from __future__ import annotations

import math
from collections import Counter

from mcp_ops_ai_agent.tool_discovery.embeddings import expanded_tokens, tokenize
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
) -> tuple[float, float]:
    lexical = lexical_score(query, document)
    metadata = metadata_score(query, document)
    combined = (
        semantic_score * semantic_weight
        + lexical * lexical_weight
        + metadata * metadata_weight
    )
    query_terms = set(tokenize(query))
    investigative_terms = {"why", "what", "show", "find", "inspect", "retrieve", "status", "failed"}
    if query_terms & investigative_terms and document.risk_level not in {"READ_ONLY", "LOW"}:
        combined -= 0.08
    if "rerun" in document.name and "rerun" not in query_terms:
        combined -= 0.12
    if "deploy" in document.name and not ({"deploy", "deployment", "staging"} & query_terms):
        combined -= 0.12
    compensation_requested = {"compensate", "compensation", "rollback"} & query_terms
    if "compensation" in document.tags and not compensation_requested:
        combined -= 0.3
    if document.name == "close_ticket_if_created_by_failed_workflow" and "close" not in query_terms:
        combined -= 0.25
    if document.name == "create_ticket" and {"create", "ticket"} <= query_terms:
        combined += 0.12
    if document.name == "create_issue" and {"create", "issue"} <= query_terms:
        combined += 0.12
    if not document.executable:
        combined -= 0.01
    return lexical, round(max(0.0, min(1.0, combined)), 4)


def explanation(query: str, document: ToolDocument) -> str:
    query_terms = set(tokenize(query))
    matches = sorted(query_terms & set(expanded_tokens(document.discovery_text)))
    if matches:
        return "Matched request terms: " + ", ".join(matches[:5]) + "."
    if document.category in query.lower():
        return f"Matched requested engineering category {document.category}."
    return "Selected by semantic similarity to the tool description and tags."
