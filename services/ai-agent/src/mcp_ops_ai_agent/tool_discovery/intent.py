from __future__ import annotations

import re
from dataclasses import dataclass, field

from mcp_ops_ai_agent.tool_discovery.embeddings import expanded_tokens, tokenize
from mcp_ops_ai_agent.tool_discovery.models import ToolDocument


@dataclass(frozen=True, slots=True)
class RetrievalIntent:
    primary_intents: frozenset[str] = frozenset()
    requested_capabilities: frozenset[str] = frozenset()
    entities: dict[str, str] = field(default_factory=dict)
    risk_preference: str = "neutral"


CAPABILITY_TERMS: dict[str, set[str]] = {
    "approval": {"approval", "approve", "permission", "authorized", "governed"},
    "build": {"build", "pipeline", "ci", "actions", "workflow", "job", "failed", "red"},
    "deployment": {
        "deploy",
        "deployment",
        "release",
        "rollout",
        "rollback",
    },
    "diagnostics": {
        "diagnose",
        "diagnostic",
        "why",
        "failure",
        "failed",
        "unhealthy",
        "error",
        "incident",
        "investigate",
    },
    "documentation": {"docs", "document", "documentation", "runbook", "guide", "procedure"},
    "logs": {"log", "logs", "trace", "error", "output", "stacktrace"},
    "operation": {"restart", "rerun", "run", "update", "delete", "restore", "execute"},
    "ownership": {"owner", "owns", "team", "service", "catalog", "escalation"},
    "repository": {
        "commit",
        "commits",
        "diff",
        "files",
        "changes",
        "changed",
        "pr",
        "pull",
        "repository",
        "repo",
    },
    "testing": {"test", "tests", "validation", "smoke", "suite", "pytest"},
    "ticket": {"ticket", "issue", "jira", "maintenance", "defect"},
    "device": {"device", "sim", "telemetry", "sensor", "service", "health"},
    "compensation": {"compensate", "compensation", "restore", "revert", "close"},
}

CATEGORY_CAPABILITIES: dict[str, set[str]] = {
    "cicd": {"build"},
    "device": {"device", "diagnostics", "operation"},
    "diagnostics": {"diagnostics", "logs", "device"},
    "knowledge": {"documentation"},
    "repository": {"repository"},
    "service_catalog": {"ownership", "documentation"},
    "ticket": {"ticket"},
}


def extract_retrieval_intent(query: str) -> RetrievalIntent:
    tokens = set(expanded_tokens(query))
    raw_tokens = set(tokenize(query))
    capabilities = {
        capability
        for capability, terms in CAPABILITY_TERMS.items()
        if tokens & terms
    }
    intents = _primary_intents(raw_tokens, capabilities)
    return RetrievalIntent(
        primary_intents=frozenset(intents),
        requested_capabilities=frozenset(capabilities),
        entities=_entities(query),
        risk_preference=_risk_preference(raw_tokens, capabilities),
    )


def document_capabilities(document: ToolDocument) -> frozenset[str]:
    capabilities = set(CATEGORY_CAPABILITIES.get(document.category, set()))
    document_terms = set(expanded_tokens(document.discovery_text))
    for capability, terms in CAPABILITY_TERMS.items():
        if document_terms & terms:
            capabilities.add(capability)
    return frozenset(capabilities)


def capability_score(intent: RetrievalIntent, document: ToolDocument) -> float:
    if not intent.requested_capabilities:
        return 0.0
    capabilities = document_capabilities(document)
    overlap = intent.requested_capabilities & capabilities
    if not overlap:
        return 0.0
    score = min(0.25, len(overlap) * 0.055)
    if intent.primary_intents & {"investigate_failure", "diagnose_issue"}:
        if {"build", "logs", "diagnostics", "repository"} & capabilities:
            score += 0.05
    if "create_record" in intent.primary_intents and "ticket" in capabilities:
        score += 0.08
    if "execute_operation" in intent.primary_intents and "operation" in capabilities:
        score += 0.06
    return round(min(score, 0.35), 4)


def capability_penalty(intent: RetrievalIntent, document: ToolDocument) -> float:
    capabilities = document_capabilities(document)
    penalty = 0.0
    operational = bool({"operation", "deployment"} & capabilities) and document.risk_level not in {
        "READ_ONLY",
        "LOW",
    }
    operation_requested = bool(
        {"operation", "approval", "compensation"} & intent.requested_capabilities
    ) or "execute_operation" in intent.primary_intents
    if operational and not operation_requested:
        penalty += 0.45
    if (
        intent.risk_preference == "investigation_first"
        and document.risk_level not in {"READ_ONLY", "LOW"}
    ):
        penalty += 0.08
    if "compensation" in capabilities and "compensation" not in intent.requested_capabilities:
        penalty += 0.25
    if not document.executable:
        penalty += 0.01
    return round(min(penalty, 0.65), 4)


def _primary_intents(tokens: set[str], capabilities: set[str]) -> set[str]:
    intents: set[str] = set()
    if {"why", "investigate", "failed", "failure", "unhealthy"} & tokens:
        intents.add("investigate_failure")
    if {"diagnose", "diagnostic", "error", "incident"} & tokens:
        intents.add("diagnose_issue")
    if {"ticket", "issue", "jira"} & tokens and {"create", "open"} & tokens:
        intents.add("create_record")
    if {"restart", "rerun", "deploy", "rollback", "update", "delete"} & tokens:
        intents.add("execute_operation")
    if "documentation" in capabilities:
        intents.add("lookup_knowledge")
    return intents


def _risk_preference(tokens: set[str], capabilities: set[str]) -> str:
    asks_to_investigate = bool({"why", "check", "inspect", "investigate", "find"} & tokens)
    asks_to_operate = bool({"restart", "rerun", "deploy", "rollback", "delete"} & tokens)
    if asks_to_investigate and not asks_to_operate:
        return "investigation_first"
    if asks_to_operate or "operation" in capabilities:
        return "operation_requested"
    return "neutral"


def _entities(query: str) -> dict[str, str]:
    entities: dict[str, str] = {}
    service_match = re.search(r"\b([a-z][a-z0-9-]+-api|payments|billing|orders)\b", query, re.I)
    if service_match:
        entities["service"] = service_match.group(1).lower()
    device_match = re.search(r"\bSIM-\d{3}\b", query, re.I)
    if device_match:
        entities["device_id"] = device_match.group(0).upper()
    repo_match = re.search(r"\b[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\b", query)
    if repo_match:
        entities["repository"] = repo_match.group(0)
    environment_terms = {"dev", "staging", "production", "prod"}
    for term in tokenize(query):
        if term in environment_terms:
            entities["environment"] = "production" if term == "prod" else term
            break
    return entities
