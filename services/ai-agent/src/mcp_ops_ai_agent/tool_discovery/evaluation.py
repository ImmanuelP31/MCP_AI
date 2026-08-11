from __future__ import annotations

import json
from pathlib import Path

from mcp_ops_ai_agent.tool_discovery.models import BenchmarkCase, BenchmarkResult
from mcp_ops_ai_agent.tool_discovery.service import ToolDiscoveryService

DEFAULT_BENCHMARK_PATH = (
    Path(__file__).resolve().parents[3] / "benchmarks" / "tool_discovery_benchmark.json"
)


def load_benchmark_cases(path: Path = DEFAULT_BENCHMARK_PATH) -> tuple[BenchmarkCase, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Tool discovery benchmark must be a list.")
    cases: list[BenchmarkCase] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Benchmark case must be an object.")
        expected = item.get("expected_tools")
        if not isinstance(expected, list) or not all(isinstance(tool, str) for tool in expected):
            raise ValueError("Benchmark expected_tools must be a string list.")
        cases.append(
            BenchmarkCase(
                case_id=str(item["case_id"]),
                query=str(item["query"]),
                expected_tools=tuple(expected),
                role=str(item.get("role", "ENGINEER")),
            )
        )
    return tuple(cases)


def evaluate_tool_discovery(
    service: ToolDiscoveryService,
    *,
    cases: tuple[BenchmarkCase, ...] | None = None,
    top_k: int = 5,
) -> BenchmarkResult:
    benchmark_cases = cases or load_benchmark_cases()
    recall_total = 0.0
    precision_total = 0.0
    reciprocal_rank_total = 0.0

    for case in benchmark_cases:
        response = service.retrieve(case.query, role=case.role, top_k=top_k)
        actual = [result.tool.name for result in response.ranked_tools]
        expected = set(case.expected_tools)
        hits = [tool for tool in actual if tool in expected]
        recall_total += len(hits) / len(expected) if expected else 0.0
        precision_total += len(hits) / top_k if top_k else 0.0
        reciprocal_rank_total += _reciprocal_rank(actual, expected)

    count = len(benchmark_cases)
    return BenchmarkResult(
        cases=count,
        recall_at_k=_ratio(recall_total, count),
        precision_at_k=_ratio(precision_total, count),
        mrr=_ratio(reciprocal_rank_total, count),
    )


def _reciprocal_rank(actual: list[str], expected: set[str]) -> float:
    for index, tool_name in enumerate(actual, start=1):
        if tool_name in expected:
            return 1.0 / index
    return 0.0


def _ratio(total: float, count: int) -> float:
    if count == 0:
        return 0.0
    return round(total / count, 3)
