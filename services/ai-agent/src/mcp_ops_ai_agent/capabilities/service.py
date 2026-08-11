from __future__ import annotations

import heapq
from collections import deque
from collections.abc import Mapping
from itertools import count

from mcp_ops_policy.tool_registry import TOOL_REGISTRY, ToolMetadata

from mcp_ops_ai_agent.capabilities.models import (
    CapabilityEdge,
    CapabilityGraphSnapshot,
    CapabilityPath,
    CapabilityPathRequest,
    ResourceNode,
)
from mcp_ops_ai_agent.workflows.models import PolicyDecision, WorkflowNode
from mcp_ops_ai_agent.workflows.policy import WorkflowPolicyEvaluator

RISK_PENALTY = {
    "READ_ONLY": 0.0,
    "LOW": 0.2,
    "MEDIUM": 1.0,
    "HIGH": 3.0,
    "CRITICAL": 8.0,
}

GOAL_TYPES = {
    "create_issue_for_latest_failed_build": "ticket",
    "deploy_to_staging": "staging_environment",
    "investigate_failed_build": "build_logs",
    "validate_deployment": "validation",
    "find_service_runbook": "documentation",
}

TOOL_RESOURCE_MAP: dict[str, tuple[str, str, list[str], float]] = {
    "get_commit_history": ("repository", "commit_history", [], 1.0),
    "get_recent_commits": ("repository", "commit_history", [], 1.0),
    "list_recent_commits": ("repository", "commit_history", [], 1.0),
    "get_changed_files": ("commit_history", "changed_files", [], 1.0),
    "summarize_diff": ("changed_files", "diff_summary", [], 1.2),
    "get_pull_request": ("repository", "pull_request", [], 1.1),
    "get_build_status": ("repository", "build_pipeline", [], 1.0),
    "get_failed_jobs": ("build_pipeline", "failed_build", [], 1.0),
    "get_pipeline_logs": ("failed_build", "build_logs", [], 1.0),
    "analyze_build_failure": ("build_logs", "failure_analysis", ["build_logs"], 1.5),
    "run_tests": ("repository", "test_result", [], 2.0),
    "rerun_build": ("failure_analysis", "build_pipeline", ["failure_analysis"], 2.0),
    "deploy_staging": ("test_result", "staging_environment", ["test_result"], 3.0),
    "get_deployment_status": ("staging_environment", "deployment", [], 1.0),
    "compare_deployments": ("deployment", "deployment_comparison", [], 1.2),
    "rollback_production": ("deployment", "production_environment", ["deployment"], 5.0),
    "delete_bad_deployment": ("deployment", "deleted_deployment", ["approval"], 8.0),
    "create_ticket": ("failure_analysis", "ticket", [], 1.2),
    "search_documentation": ("service", "documentation", [], 1.0),
    "get_runbook": ("service", "documentation", [], 1.0),
    "get_service_owner": ("service", "owner", [], 0.8),
}


class CapabilityGraphService:
    def __init__(
        self,
        *,
        registry: Mapping[str, ToolMetadata] | None = None,
        policy_evaluator: WorkflowPolicyEvaluator | None = None,
    ) -> None:
        self.registry = TOOL_REGISTRY if registry is None else registry
        self.policy_evaluator = policy_evaluator or WorkflowPolicyEvaluator(registry=self.registry)
        self.resources = _default_resources()
        self.edges = self._build_edges()

    def snapshot(self) -> CapabilityGraphSnapshot:
        return CapabilityGraphSnapshot(resources=list(self.resources.values()), edges=self.edges)

    def find_tools_reachable_from_resource(
        self,
        resource_ref: str,
        *,
        role: str = "ENGINEER",
        environment: str = "dev",
        disabled_servers: set[str] | None = None,
    ) -> list[CapabilityEdge]:
        source_type = _resource_type(resource_ref)
        return [
            edge
            for edge in self.edges
            if edge.source_type == source_type
            and self._edge_allowed(edge, role, environment, disabled_servers or set())
        ]

    def find_resources_affected_by_tool(self, tool_name: str) -> list[str]:
        return [
            edge.destination_type
            for edge in self.edges
            if edge.tool_name == tool_name and edge.enabled
        ]

    def find_path(self, request: CapabilityPathRequest) -> CapabilityPath:
        goal_type = GOAL_TYPES.get(request.goal, request.goal)
        source_type = _resource_type(request.source)
        disabled = set(request.disabled_servers)
        if request.strategy == "lowest_risk":
            return self._dijkstra(request, source_type, goal_type, disabled, risk_weight=True)
        if request.strategy == "shortest":
            return self._bfs(request, source_type, goal_type, disabled, policy_filter=False)
        return self._dijkstra(request, source_type, goal_type, disabled, risk_weight=False)

    def path_request_for_goal(
        self,
        user_request: str,
        *,
        role: str,
        environment: str,
    ) -> CapabilityPathRequest:
        return CapabilityPathRequest(
            source=_infer_source(user_request),
            goal=_infer_goal(user_request),
            role=role,
            environment=environment,
        )

    def constrain_tool_sequence(
        self,
        *,
        user_request: str,
        role: str,
        environment: str,
        available_tool_names: list[str],
    ) -> list[str]:
        request = CapabilityPathRequest(
            source=_infer_source(user_request),
            goal=_infer_goal(user_request),
            role=role,
            environment=environment,
        )
        path = self.find_path(request)
        ordered = [tool for tool in path.tools if tool in set(available_tool_names)]
        return [*ordered, *[tool for tool in available_tool_names if tool not in set(ordered)]]

    def _build_edges(self) -> list[CapabilityEdge]:
        edges: list[CapabilityEdge] = []
        for tool_name, metadata in sorted(self.registry.items()):
            declarations = _declarations_for(tool_name, metadata)
            for source_type, destination_type, prerequisites, cost in declarations:
                edges.append(
                    CapabilityEdge(
                        source_type=source_type,
                        destination_type=destination_type,
                        tool_name=tool_name,
                        mcp_server=metadata.server,
                        cost=metadata.cost_weight if metadata.cost_weight != 1.0 else cost,
                        risk=metadata.risk_level.value,
                        prerequisites=prerequisites,
                        enabled=metadata.enabled,
                    )
                )
        return edges

    def _bfs(
        self,
        request: CapabilityPathRequest,
        source_type: str,
        goal_type: str,
        disabled_servers: set[str],
        *,
        policy_filter: bool,
    ) -> CapabilityPath:
        queue: deque[tuple[str, list[str], list[CapabilityEdge]]] = deque(
            [(source_type, [source_type], [])]
        )
        visited: set[str] = set()
        while queue:
            current, nodes, edges = queue.popleft()
            if current == goal_type:
                return _path_from_edges(request, nodes, edges)
            if current in visited:
                continue
            visited.add(current)
            for edge in self._outgoing(current):
                if policy_filter and not self._edge_allowed(
                    edge, request.role, request.environment, disabled_servers
                ):
                    continue
                if edge.destination_type not in nodes:
                    queue.append(
                        (edge.destination_type, [*nodes, edge.destination_type], [*edges, edge])
                    )
        return _unreachable(request, source_type, goal_type)

    def _dijkstra(
        self,
        request: CapabilityPathRequest,
        source_type: str,
        goal_type: str,
        disabled_servers: set[str],
        *,
        risk_weight: bool,
    ) -> CapabilityPath:
        sequence = count()
        heap: list[tuple[float, int, str, list[str], list[CapabilityEdge]]] = [
            (0.0, next(sequence), source_type, [source_type], [])
        ]
        best: dict[str, float] = {}
        while heap:
            cost, _, current, nodes, edges = heapq.heappop(heap)
            if current == goal_type:
                return _path_from_edges(request, nodes, edges)
            if best.get(current, float("inf")) <= cost:
                continue
            best[current] = cost
            for edge in self._outgoing(current):
                if not self._edge_allowed(
                    edge, request.role, request.environment, disabled_servers
                ):
                    continue
                if edge.destination_type in nodes:
                    continue
                next_cost = cost + _edge_score(edge, risk_weight=risk_weight)
                heapq.heappush(
                    heap,
                    (
                        next_cost,
                        next(sequence),
                        edge.destination_type,
                        [*nodes, edge.destination_type],
                        [*edges, edge],
                    ),
                )
        return _unreachable(request, source_type, goal_type)

    def _outgoing(self, resource_type: str) -> list[CapabilityEdge]:
        return [edge for edge in self.edges if edge.source_type == resource_type and edge.enabled]

    def _edge_allowed(
        self,
        edge: CapabilityEdge,
        role: str,
        environment: str,
        disabled_servers: set[str],
    ) -> bool:
        if edge.mcp_server in disabled_servers:
            return False
        evaluation = self.policy_evaluator.evaluate(
            WorkflowNode(
                id=f"capability-{edge.tool_name}",
                tool_name=edge.tool_name,
                tool_server=edge.mcp_server,
                description=f"Capability graph edge for {edge.tool_name}.",
                arguments=_arguments_for_edge(edge),
                risk_level=edge.risk,
            ),
            actor="capability-graph",
            role=role,
            environment=environment,
            phase="planning",
        )
        return evaluation.decision in {
            PolicyDecision.ALLOW,
            PolicyDecision.ALLOW_WITH_APPROVAL,
        }


def _default_resources() -> dict[str, ResourceNode]:
    resources = [
        ResourceNode(id="role:developer", type="role", name="developer"),
        ResourceNode(id="repository:payments-api", type="repository", name="payments-api"),
        ResourceNode(id="repository:orders-api", type="repository", name="orders-api"),
        ResourceNode(id="service:payments", type="service", name="payments"),
        ResourceNode(
            id="build_pipeline:payments-api",
            type="build_pipeline",
            name="payments-api-ci",
        ),
        ResourceNode(id="failed_build:latest", type="failed_build", name="latest failed build"),
        ResourceNode(id="build_logs:latest", type="build_logs", name="latest build logs"),
        ResourceNode(
            id="failure_analysis:latest",
            type="failure_analysis",
            name="failure analysis",
        ),
        ResourceNode(id="ticket:maintenance", type="ticket", name="maintenance issue"),
        ResourceNode(
            id="staging_environment:staging",
            type="staging_environment",
            name="staging",
            environment="staging",
        ),
        ResourceNode(
            id="production_environment:production",
            type="production_environment",
            name="production",
            environment="production",
        ),
        ResourceNode(id="documentation:runbook", type="documentation", name="engineering runbook"),
    ]
    return {resource.id: resource for resource in resources}


def _declarations_for(
    tool_name: str,
    metadata: ToolMetadata,
) -> list[tuple[str, str, list[str], float]]:
    if metadata.input_resource_types and metadata.output_resource_types:
        return [
            (source, destination, metadata.preconditions, metadata.cost_weight)
            for source in metadata.input_resource_types
            for destination in metadata.output_resource_types
        ]
    declaration = TOOL_RESOURCE_MAP.get(tool_name)
    return [declaration] if declaration else []


def _resource_type(resource_ref: str) -> str:
    if ":" in resource_ref:
        return resource_ref.split(":", maxsplit=1)[0]
    return resource_ref


def _path_from_edges(
    request: CapabilityPathRequest,
    nodes: list[str],
    edges: list[CapabilityEdge],
) -> CapabilityPath:
    total_cost = sum(_edge_score(edge, risk_weight=False) for edge in edges)
    risk_score = sum(RISK_PENALTY.get(edge.risk, 10.0) for edge in edges)
    return CapabilityPath(
        source=request.source,
        goal=request.goal,
        reachable=True,
        nodes=nodes,
        edges=edges,
        tools=[edge.tool_name for edge in edges],
        total_cost=round(total_cost, 3),
        risk_score=round(risk_score, 3),
        explanation="Capability path found through registered MCP tool edges.",
        alternatives=[],
    )


def _unreachable(
    request: CapabilityPathRequest,
    source_type: str,
    goal_type: str,
) -> CapabilityPath:
    return CapabilityPath(
        source=request.source,
        goal=request.goal,
        reachable=False,
        nodes=[source_type],
        explanation=f"No policy-compliant path from {source_type} to {goal_type}.",
        policy_compliant=False,
    )


def _edge_score(edge: CapabilityEdge, *, risk_weight: bool) -> float:
    risk_penalty = (
        RISK_PENALTY.get(edge.risk, 10.0)
        if risk_weight
        else RISK_PENALTY.get(edge.risk, 10.0) * 0.25
    )
    latency_penalty = 0.1 if edge.mcp_server.endswith("-mcp") else 0.2
    return edge.cost + risk_penalty + latency_penalty


def _arguments_for_edge(edge: CapabilityEdge) -> dict[str, object]:
    if edge.tool_name in {"restart_service", "restart_device", "update_device_configuration"}:
        return {
            "device_id": "SIM-014",
            "service_name": "sensor-ingestor",
            "reason": "Capability graph policy evaluation.",
        }
    if edge.tool_name == "create_ticket":
        return {
            "device_id": "SIM-014",
            "title": "Capability graph issue",
            "description": "Capability graph generated issue path.",
            "priority": "HIGH",
            "team": "Engineering Operations",
            "diagnostic_evidence": {"source": "capability_graph"},
        }
    if "deployment" in edge.tool_name or edge.destination_type.endswith("environment"):
        return {"deployment_id": "deploy-2026-08-11", "repository": "payments-api"}
    return {"query": "capability graph"}


def _infer_source(user_request: str) -> str:
    normalized = user_request.lower()
    if "sim-" in normalized or "device" in normalized:
        return "device:SIM-014"
    if "service" in normalized or "runbook" in normalized:
        return "service:payments"
    return "repository:payments-api"


def _infer_goal(user_request: str) -> str:
    normalized = user_request.lower()
    if "ticket" in normalized or "issue" in normalized:
        return "create_issue_for_latest_failed_build"
    if "staging" in normalized or "deploy" in normalized:
        return "deploy_to_staging"
    if "runbook" in normalized or "documentation" in normalized:
        return "find_service_runbook"
    if "build" in normalized or "pipeline" in normalized:
        return "investigate_failed_build"
    return "investigate_failed_build"
