from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolDocument:
    name: str
    description: str
    server: str
    category: str
    risk_level: str
    required_permission: str
    required_roles: tuple[str, ...]
    input_schema: dict[str, Any]
    tags: tuple[str, ...]
    executable: bool
    enabled: bool
    embedding: tuple[float, ...] = field(default_factory=tuple)

    @property
    def discovery_text(self) -> str:
        return " ".join(
            [
                self.name.replace("_", " "),
                self.description,
                self.server,
                self.category,
                self.risk_level,
                self.required_permission,
                " ".join(self.required_roles),
                " ".join(self.tags),
                " ".join(str(key) for key in self.input_schema.get("properties", {})),
            ]
        )

    def as_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "server": self.server,
            "category": self.category,
            "risk_level": self.risk_level,
            "required_permission": self.required_permission,
            "required_roles": list(self.required_roles),
            "input_schema": self.input_schema,
            "tags": list(self.tags),
            "executable": self.executable,
            "enabled": self.enabled,
        }


@dataclass(frozen=True, slots=True)
class ToolDiscoveryFilters:
    allowed_servers: frozenset[str] = frozenset()
    allowed_categories: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class ToolDiscoveryRequest:
    query: str
    role: str
    top_k: int = 8
    minimum_score: float = 0.0
    filters: ToolDiscoveryFilters = field(default_factory=ToolDiscoveryFilters)


@dataclass(frozen=True, slots=True)
class ToolDiscoveryResult:
    tool: ToolDocument
    semantic_score: float
    lexical_score: float
    combined_score: float
    authorization_status: str
    explanation: str

    def as_payload(self) -> dict[str, Any]:
        return {
            **self.tool.as_payload(),
            "semantic_score": self.semantic_score,
            "lexical_score": self.lexical_score,
            "combined_score": self.combined_score,
            "authorization_status": self.authorization_status,
            "explanation": self.explanation,
        }


@dataclass(frozen=True, slots=True)
class ToolDiscoveryResponse:
    query: str
    role: str
    ranked_tools: list[ToolDiscoveryResult]
    filtered_out_unauthorized: int
    index_backend: str

    def as_payload(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "role": self.role,
            "ranked_tools": [result.as_payload() for result in self.ranked_tools],
            "filtered_out_unauthorized": self.filtered_out_unauthorized,
            "index_backend": self.index_backend,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    case_id: str
    query: str
    expected_tools: tuple[str, ...]
    role: str = "ENGINEER"


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    cases: int
    recall_at_k: float
    precision_at_k: float
    mrr: float
    recall_at_1: float = 0.0
    recall_at_3: float = 0.0
    recall_at_5: float = 0.0

    def as_payload(self) -> dict[str, float | int]:
        return {
            "cases": self.cases,
            "recall_at_k": self.recall_at_k,
            "precision_at_k": self.precision_at_k,
            "mrr": self.mrr,
            "recall_at_1": self.recall_at_1,
            "recall_at_3": self.recall_at_3,
            "recall_at_5": self.recall_at_5,
        }
