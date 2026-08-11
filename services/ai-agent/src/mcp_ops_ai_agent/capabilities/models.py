from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ResourceNode(StrictModel):
    id: str = Field(min_length=1, max_length=160)
    type: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)
    environment: str | None = Field(default=None, max_length=64)


class CapabilityEdge(StrictModel):
    source_type: str = Field(min_length=1, max_length=80)
    destination_type: str = Field(min_length=1, max_length=80)
    tool_name: str = Field(min_length=1, max_length=128)
    mcp_server: str = Field(min_length=1, max_length=128)
    cost: float = Field(ge=0.0)
    risk: str = Field(min_length=1, max_length=32)
    prerequisites: list[str] = Field(default_factory=list)
    enabled: bool = True


class CapabilityPathRequest(StrictModel):
    source: str = Field(min_length=1, max_length=180)
    goal: str = Field(min_length=1, max_length=180)
    role: str = Field(default="ENGINEER", min_length=1, max_length=64)
    environment: str = Field(default="dev", min_length=1, max_length=64)
    strategy: str = Field(default="policy_compliant", min_length=1, max_length=64)
    disabled_servers: list[str] = Field(default_factory=list, max_length=20)


class CapabilityPath(StrictModel):
    source: str
    goal: str
    reachable: bool
    nodes: list[str] = Field(default_factory=list)
    edges: list[CapabilityEdge] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    total_cost: float = 0.0
    risk_score: float = 0.0
    policy_compliant: bool = True
    explanation: str
    alternatives: list[list[str]] = Field(default_factory=list)

    def as_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class CapabilityGraphSnapshot(StrictModel):
    resources: list[ResourceNode]
    edges: list[CapabilityEdge]

    def as_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class CapabilityEvaluationResult(StrictModel):
    cases: int
    llm_only_valid_tool_sequence_rate: float
    graph_valid_tool_sequence_rate: float
    llm_only_hallucinated_tool_rate: float
    graph_hallucinated_tool_rate: float
    llm_only_policy_violation_rate: float
    graph_policy_violation_rate: float
    llm_only_unnecessary_tool_count: int
    graph_unnecessary_tool_count: int

    def as_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
