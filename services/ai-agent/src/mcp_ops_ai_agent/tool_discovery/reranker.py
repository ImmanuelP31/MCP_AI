from __future__ import annotations

from dataclasses import replace

from mcp_ops_ai_agent.tool_discovery.embeddings import tokenize
from mcp_ops_ai_agent.tool_discovery.intent import (
    RetrievalIntent,
    capability_penalty,
    capability_score,
    document_capabilities,
)
from mcp_ops_ai_agent.tool_discovery.models import ToolDiscoveryResult, ToolDocument

RUNTIME_REFERENCE_FIELDS = {
    "base",
    "head",
    "job_id",
    "pull_number",
    "run_id",
    "sha",
    "ticket_id",
}


def rerank_results(
    query: str,
    intent: RetrievalIntent,
    results: list[ToolDiscoveryResult],
    *,
    top_k: int,
) -> list[ToolDiscoveryResult]:
    """Second-stage deterministic reranker for planner-visible MCP tools.

    The first retrieval stage should optimize recall. This stage reorders the shortlist using
    higher-level intent and capability signals so action tools do not beat investigative tools
    merely because they share words like "pipeline" or "deployment".
    """

    reranked = [
        _with_rerank_score(query, intent, result)
        for result in results
    ]
    ordered = sorted(
        reranked,
        key=lambda item: (
            -item.combined_score,
            -item.semantic_score,
            -item.lexical_score,
            item.tool.name,
        ),
    )
    return ordered[:top_k]


def rerank_score(query: str, intent: RetrievalIntent, result: ToolDiscoveryResult) -> float:
    document = result.tool
    score = result.combined_score * 0.72
    score += _description_match_boost(query, document)
    score += capability_score(intent, document)
    score += _schema_compatibility_score(intent, document)
    score += _intent_alignment_score(intent, document)
    score += _dependency_usefulness_score(intent, document)
    score -= capability_penalty(intent, document)
    return round(max(0.0, min(1.0, score)), 4)


def _with_rerank_score(
    query: str,
    intent: RetrievalIntent,
    result: ToolDiscoveryResult,
) -> ToolDiscoveryResult:
    score = rerank_score(query, intent, result)
    return replace(
        result,
        combined_score=score,
        explanation=_rerank_explanation(result.explanation, intent, result.tool),
    )


def _description_match_boost(query: str, document: ToolDocument) -> float:
    query_terms = set(tokenize(query))
    name_terms = set(tokenize(document.name))
    tag_terms = {term for tag in document.tags for term in tokenize(tag)}
    description_terms = set(tokenize(document.description))
    boost = 0.0
    if query_terms & name_terms:
        boost += 0.04
    if query_terms & tag_terms:
        boost += 0.035
    if query_terms & description_terms:
        boost += 0.025
    return round(min(boost, 0.08), 4)


def _schema_compatibility_score(intent: RetrievalIntent, document: ToolDocument) -> float:
    properties = document.input_schema.get("properties", {})
    required = document.input_schema.get("required", [])
    if not isinstance(properties, dict):
        return 0.0
    if not isinstance(required, list):
        required = []
    property_names = set(properties)
    boost = 0.0
    if "repository" in intent.entities and "repository" in property_names:
        boost += 0.04
    if "device_id" in intent.entities and "device_id" in property_names:
        boost += 0.04
    if "environment" in intent.entities and "environment" in property_names:
        boost += 0.03
    if "service" in intent.entities and {"service_name", "repository"} & property_names:
        boost += 0.025

    required_fields = {
        str(field)
        for field in required
        if str(field) not in {"actor_role", "approval_token"}
    }
    unresolved = required_fields - set(intent.entities) - {"repository"}
    unresolved_runtime_fields = unresolved & RUNTIME_REFERENCE_FIELDS
    unresolved_other_fields = unresolved - unresolved_runtime_fields
    penalty = min(0.08, len(unresolved_other_fields) * 0.025)
    if unresolved_runtime_fields and not _has_dependency_context(intent, document):
        penalty += min(0.06, len(unresolved_runtime_fields) * 0.02)
    return round(max(-0.1, min(0.1, boost - penalty)), 4)


def _intent_alignment_score(intent: RetrievalIntent, document: ToolDocument) -> float:
    capabilities = document_capabilities(document)
    score = 0.0
    if intent.risk_preference == "investigation_first":
        if document.risk_level in {"READ_ONLY", "LOW"}:
            score += 0.06
        elif {"operation", "deployment", "compensation"} & capabilities:
            score -= 0.22
    if "execute_operation" in intent.primary_intents:
        if {"operation", "deployment"} & capabilities:
            score += 0.08
        if (
            document.risk_level in {"HIGH", "CRITICAL"}
            and "approval" in intent.requested_capabilities
        ):
            score += 0.04
    if "create_record" in intent.primary_intents and "ticket" in capabilities:
        score += 0.06
    return round(max(-0.15, min(0.15, score)), 4)


def _dependency_usefulness_score(intent: RetrievalIntent, document: ToolDocument) -> float:
    capabilities = document_capabilities(document)
    score = 0.0
    if "investigate_failure" in intent.primary_intents:
        if "build" in capabilities:
            score += 0.05
        if "logs" in capabilities:
            score += 0.055
        if "repository" in capabilities:
            score += 0.04
        if "diagnostics" in capabilities:
            score += 0.035
    if "deployment" in intent.requested_capabilities and "logs" in capabilities:
        score += 0.04
    if "testing" in intent.requested_capabilities and "testing" in capabilities:
        score += 0.05
    return round(min(score, 0.14), 4)


def _has_dependency_context(intent: RetrievalIntent, document: ToolDocument) -> bool:
    capabilities = document_capabilities(document)
    return bool({"build", "repository", "logs", "deployment"} & intent.requested_capabilities) and (
        bool({"build", "repository", "logs", "deployment"} & capabilities)
    )


def _rerank_explanation(
    base_explanation: str,
    intent: RetrievalIntent,
    document: ToolDocument,
) -> str:
    overlap = sorted(intent.requested_capabilities & document_capabilities(document))
    if not overlap:
        return base_explanation
    return f"{base_explanation} Reranked for capability fit: {', '.join(overlap[:4])}."
