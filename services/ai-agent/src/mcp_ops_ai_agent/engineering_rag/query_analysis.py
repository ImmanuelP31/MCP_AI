from __future__ import annotations

import re
from dataclasses import dataclass

from mcp_ops_ai_agent.engineering_rag.models import KnowledgeFilters
from mcp_ops_ai_agent.tool_discovery.embeddings import expanded_tokens, tokenize


@dataclass(frozen=True, slots=True)
class RagQueryAnalysis:
    semantic_query: str
    service: str | None
    repository: str | None
    environment: str | None
    likely_document_types: tuple[str, ...]
    required_capabilities: tuple[str, ...]


DOCUMENT_TYPE_TERMS: dict[str, set[str]] = {
    "api": {"api", "endpoint", "contract", "schema"},
    "cicd": {"build", "ci", "pipeline", "job", "workflow", "failed", "failure", "logs"},
    "deployment": {"deploy", "deployment", "release", "rollout", "rollback", "staging"},
    "environment_policy": {"environment", "prod", "production", "staging", "restriction"},
    "mcp_tools": {"tool", "tools", "mcp", "approved"},
    "ownership": {"owner", "owns", "team", "escalation"},
    "policy": {"policy", "required", "requires", "rule", "approval"},
    "run_instructions": {"run", "local", "docker", "compose", "setup", "start"},
    "testing": {"test", "tests", "testing", "validation", "smoke", "suite"},
}

CAPABILITY_TERMS: dict[str, set[str]] = {
    "approval": {"approval", "approve", "permission"},
    "cicd": {"build", "pipeline", "ci", "workflow", "job", "failed", "failure"},
    "deployment": {"deploy", "deployment", "release", "rollout", "rollback"},
    "documentation": {"document", "docs", "guide", "runbook", "procedure"},
    "environment": {"environment", "staging", "production", "prod"},
    "ownership": {"owner", "owns", "team", "escalation"},
    "policy": {"policy", "restriction", "required", "requires"},
    "repository": {"repo", "repository", "commit", "diff", "changes", "files"},
    "run_instructions": {"run", "local", "docker", "compose", "setup"},
    "testing": {"test", "tests", "validation", "smoke", "suite"},
}


def analyze_rag_query(query: str, filters: KnowledgeFilters) -> RagQueryAnalysis:
    raw_terms = set(tokenize(query))
    expanded = set(expanded_tokens(query))
    service = filters.service or _service(query)
    repository = filters.repository or _repository(query) or service
    environment = filters.environment or _environment(query)
    document_types = _document_types(raw_terms, expanded, filters.document_type)
    capabilities = _capabilities(raw_terms, expanded)
    semantic_query = _semantic_query(query, service, repository, environment)
    return RagQueryAnalysis(
        semantic_query=semantic_query,
        service=service,
        repository=repository,
        environment=environment,
        likely_document_types=tuple(document_types),
        required_capabilities=tuple(capabilities),
    )


def analysis_filters(analysis: RagQueryAnalysis, original: KnowledgeFilters) -> KnowledgeFilters:
    return KnowledgeFilters(
        document_type=original.document_type,
        service=original.service or analysis.service,
        repository=original.repository or analysis.repository,
        environment=original.environment or analysis.environment,
        include_stale=original.include_stale,
    )


def _document_types(
    raw_terms: set[str],
    expanded_terms: set[str],
    requested_type: str | None,
) -> list[str]:
    if requested_type:
        return [requested_type]
    matched = [
        document_type
        for document_type, terms in DOCUMENT_TYPE_TERMS.items()
        if raw_terms & terms or expanded_terms & terms
    ]
    if {"why", "failed", "failure"} & raw_terms and "cicd" not in matched:
        matched.append("cicd")
    if "deployment" in matched and "environment_policy" not in matched:
        matched.append("environment_policy")
    return _ordered_unique(matched)


def _capabilities(raw_terms: set[str], expanded_terms: set[str]) -> list[str]:
    matched = [
        capability
        for capability, terms in CAPABILITY_TERMS.items()
        if raw_terms & terms or expanded_terms & terms
    ]
    if {"why", "failed", "failure"} & raw_terms and "cicd" not in matched:
        matched.append("cicd")
    return _ordered_unique(matched)


def _semantic_query(
    query: str,
    service: str | None,
    repository: str | None,
    environment: str | None,
) -> str:
    cleaned = query
    for value in (service, repository, environment):
        if value:
            cleaned = re.sub(re.escape(value), " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(prod|production|staging|dev)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or query


def _service(query: str) -> str | None:
    match = re.search(
        r"\b(payments-api|orders-api|inventory-api|billing-worker|identity-service|"
        r"notifications-api|search-service|analytics-pipeline|reporting-api|gateway-service|"
        r"payments|orders|inventory)\b",
        query,
        re.IGNORECASE,
    )
    if not match:
        return None
    value = match.group(1).lower()
    return value if value.endswith(("-api", "-worker", "-service", "-pipeline")) else f"{value}-api"


def _repository(query: str) -> str | None:
    match = re.search(r"\b[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\b", query)
    if match:
        return match.group(0)
    return None


def _environment(query: str) -> str | None:
    for term in tokenize(query):
        if term in {"prod", "production"}:
            return "production"
        if term in {"staging", "dev"}:
            return term
    return None


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
