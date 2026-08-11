from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MetricInputs:
    expected_tools: list[str]
    acceptable_tools: list[str]
    actual_tools: list[str]
    prohibited_tools: list[str]
    required_approvals: list[str]
    actual_approvals: list[str]
    relevant_documents: list[str]
    retrieved_documents: list[str]
    workflow_valid: bool
    workflow_completed: bool
    execution_succeeded: bool
    planner_latency_ms: float
    end_to_end_latency_ms: float
    token_usage: int
    estimated_cost_usd: float | None


@dataclass(frozen=True, slots=True)
class EvaluationSummary:
    cases: int
    config: str
    mode: str
    tool_recall: float
    tool_precision: float
    exact_tool_set_accuracy: float
    workflow_validity_rate: float
    workflow_completion_rate: float
    hallucinated_tool_rate: float
    unnecessary_tool_call_rate: float
    policy_violation_attempt_rate: float
    approval_classification_accuracy: float
    rag_recall_at_k: float
    rag_mrr: float
    average_workflow_length: float
    execution_success_rate: float
    planner_latency_ms: float
    end_to_end_latency_ms: float
    token_usage: int
    estimated_model_cost_usd: float | None

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)


def recall(expected: set[str], actual: set[str]) -> float:
    return 1.0 if not expected else len(expected & actual) / len(expected)


def precision(allowed: set[str], actual: list[str]) -> float:
    return 1.0 if not actual else len([tool for tool in actual if tool in allowed]) / len(actual)


def exact_tool_set_accuracy(expected: set[str], actual: set[str]) -> float:
    return float(expected == actual)


def mean_reciprocal_rank(expected: set[str], ranked: list[str]) -> float:
    for index, item in enumerate(ranked, start=1):
        if item in expected:
            return 1.0 / index
    return 0.0


def compute_summary(
    *,
    config: str,
    mode: str,
    inputs: list[MetricInputs],
) -> EvaluationSummary:
    cases = len(inputs)
    if cases == 0:
        return EvaluationSummary(
            cases=0,
            config=config,
            mode=mode,
            tool_recall=0.0,
            tool_precision=0.0,
            exact_tool_set_accuracy=0.0,
            workflow_validity_rate=0.0,
            workflow_completion_rate=0.0,
            hallucinated_tool_rate=0.0,
            unnecessary_tool_call_rate=0.0,
            policy_violation_attempt_rate=0.0,
            approval_classification_accuracy=0.0,
            rag_recall_at_k=0.0,
            rag_mrr=0.0,
            average_workflow_length=0.0,
            execution_success_rate=0.0,
            planner_latency_ms=0.0,
            end_to_end_latency_ms=0.0,
            token_usage=0,
            estimated_model_cost_usd=None,
        )

    tool_recall_total = 0.0
    tool_precision_total = 0.0
    exact_total = 0.0
    valid_total = 0
    completed_total = 0
    hallucinated = 0
    unnecessary = 0
    policy_violations = 0
    approval_correct = 0
    rag_recall_total = 0.0
    rag_mrr_total = 0.0
    workflow_length_total = 0
    execution_success_total = 0
    planner_latency_total = 0.0
    e2e_latency_total = 0.0
    token_total = 0
    cost_values: list[float] = []

    for item in inputs:
        expected = set(item.expected_tools)
        allowed = expected | set(item.acceptable_tools)
        actual = list(dict.fromkeys(item.actual_tools))
        actual_set = set(actual)
        tool_recall_total += recall(expected, actual_set)
        tool_precision_total += precision(allowed, actual)
        exact_total += exact_tool_set_accuracy(expected, actual_set)
        valid_total += int(item.workflow_valid)
        completed_total += int(item.workflow_completed)
        hallucinated += len([tool for tool in actual if tool not in allowed])
        unnecessary += len([tool for tool in actual if tool in allowed - expected])
        policy_violations += len([tool for tool in actual if tool in set(item.prohibited_tools)])
        approval_correct += int(set(item.required_approvals) == set(item.actual_approvals))
        rag_recall_total += recall(set(item.relevant_documents), set(item.retrieved_documents))
        rag_mrr_total += mean_reciprocal_rank(
            set(item.relevant_documents),
            item.retrieved_documents,
        )
        workflow_length_total += len(actual)
        execution_success_total += int(item.execution_succeeded)
        planner_latency_total += item.planner_latency_ms
        e2e_latency_total += item.end_to_end_latency_ms
        token_total += item.token_usage
        if item.estimated_cost_usd is not None:
            cost_values.append(item.estimated_cost_usd)

    total_tool_calls = max(1, workflow_length_total)
    estimated_cost = round(sum(cost_values), 6) if cost_values else None
    return EvaluationSummary(
        cases=cases,
        config=config,
        mode=mode,
        tool_recall=_round(tool_recall_total / cases),
        tool_precision=_round(tool_precision_total / cases),
        exact_tool_set_accuracy=_round(exact_total / cases),
        workflow_validity_rate=_round(valid_total / cases),
        workflow_completion_rate=_round(completed_total / cases),
        hallucinated_tool_rate=_round(hallucinated / total_tool_calls),
        unnecessary_tool_call_rate=_round(unnecessary / total_tool_calls),
        policy_violation_attempt_rate=_round(policy_violations / cases),
        approval_classification_accuracy=_round(approval_correct / cases),
        rag_recall_at_k=_round(rag_recall_total / cases),
        rag_mrr=_round(rag_mrr_total / cases),
        average_workflow_length=_round(workflow_length_total / cases),
        execution_success_rate=_round(execution_success_total / cases),
        planner_latency_ms=_round(planner_latency_total / cases),
        end_to_end_latency_ms=_round(e2e_latency_total / cases),
        token_usage=token_total,
        estimated_model_cost_usd=estimated_cost,
    )


def _round(value: float) -> float:
    return round(value, 4)
