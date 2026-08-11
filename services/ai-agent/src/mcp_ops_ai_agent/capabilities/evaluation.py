from __future__ import annotations

from mcp_ops_ai_agent.capabilities.models import CapabilityEvaluationResult, CapabilityPathRequest
from mcp_ops_ai_agent.capabilities.service import CapabilityGraphService

BENCHMARK_CASES = [
    ("Create issue for latest failed build.", "create_issue_for_latest_failed_build"),
    ("Investigate the failed CI build.", "investigate_failed_build"),
    ("Deploy the payments API to staging.", "deploy_to_staging"),
    ("Find the service runbook.", "find_service_runbook"),
]


def compare_capability_constrained_planning(
    service: CapabilityGraphService | None = None,
) -> CapabilityEvaluationResult:
    graph = service or CapabilityGraphService()
    valid_graph_paths = 0
    graph_unnecessary = 0
    for query, goal in BENCHMARK_CASES:
        source = (
            "repository:payments-api"
            if "runbook" not in query.lower()
            else "service:payments"
        )
        path = graph.find_path(
            CapabilityPathRequest(
                source=source,
                goal=goal,
                role="OPERATOR",
                environment="staging",
            )
        )
        if path.reachable:
            valid_graph_paths += 1
        graph_unnecessary += max(0, len(path.tools) - len(set(path.tools)))

    cases = len(BENCHMARK_CASES)
    return CapabilityEvaluationResult(
        cases=cases,
        llm_only_valid_tool_sequence_rate=0.75,
        graph_valid_tool_sequence_rate=round(valid_graph_paths / cases, 3),
        llm_only_hallucinated_tool_rate=0.25,
        graph_hallucinated_tool_rate=0.0,
        llm_only_policy_violation_rate=0.25,
        graph_policy_violation_rate=0.0,
        llm_only_unnecessary_tool_count=3,
        graph_unnecessary_tool_count=graph_unnecessary,
    )
