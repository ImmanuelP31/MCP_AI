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
    provider_success: bool = True
    unknown_or_disallowed_tools: int = 0


@dataclass(frozen=True, slots=True)
class EvaluationSummary:
    cases: int
    config: str
    mode: str
    provider_successful_cases: int
    provider_failed_cases: int
    provider_success_rate: float
    tool_recall: float
    tool_precision: float
    exact_tool_set_accuracy: float
    workflow_validity_rate: float
    workflow_completion_rate: float
    hallucinated_tool_rate: float
    benchmark_unexpected_tool_rate: float
    unknown_or_disallowed_tool_rate: float
    unknown_tool_call_rate: float
    cases_with_unknown_tools_rate: float
    unknown_or_disallowed_tools_per_case: float
    unnecessary_tool_call_rate: float
    policy_violation_attempt_rate: float
    approval_classification_accuracy: float
    rag_recall_at_k: float
    rag_mrr: float
    average_workflow_length: float
    execution_success_rate: float
    end_to_end_workflow_validity_rate: float
    end_to_end_workflow_completion_rate: float
    end_to_end_execution_success_rate: float
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
            provider_successful_cases=0,
            provider_failed_cases=0,
            provider_success_rate=0.0,
            tool_recall=0.0,
            tool_precision=0.0,
            exact_tool_set_accuracy=0.0,
            workflow_validity_rate=0.0,
            workflow_completion_rate=0.0,
            hallucinated_tool_rate=0.0,
            benchmark_unexpected_tool_rate=0.0,
            unknown_or_disallowed_tool_rate=0.0,
            unknown_tool_call_rate=0.0,
            cases_with_unknown_tools_rate=0.0,
            unknown_or_disallowed_tools_per_case=0.0,
            unnecessary_tool_call_rate=0.0,
            policy_violation_attempt_rate=0.0,
            approval_classification_accuracy=0.0,
            rag_recall_at_k=0.0,
            rag_mrr=0.0,
            average_workflow_length=0.0,
            execution_success_rate=0.0,
            end_to_end_workflow_validity_rate=0.0,
            end_to_end_workflow_completion_rate=0.0,
            end_to_end_execution_success_rate=0.0,
            planner_latency_ms=0.0,
            end_to_end_latency_ms=0.0,
            token_usage=0,
            estimated_model_cost_usd=None,
        )

    provider_inputs = [item for item in inputs if item.provider_success]
    provider_cases = len(provider_inputs)
    provider_failed_cases = cases - provider_cases

    tool_recall_total = 0.0
    tool_precision_total = 0.0
    exact_total = 0.0
    valid_total = 0
    completed_total = 0
    benchmark_unexpected = 0
    unknown_or_disallowed = 0
    cases_with_unknown_tools = 0
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

    end_to_end_valid_total = sum(int(item.workflow_valid) for item in inputs)
    end_to_end_completed_total = sum(int(item.workflow_completed) for item in inputs)
    end_to_end_execution_success_total = sum(int(item.execution_succeeded) for item in inputs)

    for item in provider_inputs:
        expected = set(item.expected_tools)
        allowed = expected | set(item.acceptable_tools)
        actual = list(dict.fromkeys(item.actual_tools))
        actual_set = set(actual)
        tool_recall_total += recall(expected, actual_set)
        tool_precision_total += precision(allowed, actual)
        exact_total += exact_tool_set_accuracy(expected, actual_set)
        valid_total += int(item.workflow_valid)
        completed_total += int(item.workflow_completed)
        benchmark_unexpected += len([tool for tool in actual if tool not in allowed])
        unknown_or_disallowed += item.unknown_or_disallowed_tools
        cases_with_unknown_tools += int(item.unknown_or_disallowed_tools > 0)
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

    denominator = max(1, provider_cases)
    total_tool_calls = max(1, workflow_length_total)
    total_generated_tool_attempts = max(1, workflow_length_total + unknown_or_disallowed)
    estimated_cost = round(sum(cost_values), 6) if cost_values else None
    benchmark_unexpected_rate = _round(benchmark_unexpected / total_tool_calls)
    unknown_tool_call_rate = _round(unknown_or_disallowed / total_generated_tool_attempts)
    cases_with_unknown_tools_rate = _round(cases_with_unknown_tools / denominator)
    unknown_or_disallowed_tools_per_case = _round(unknown_or_disallowed / denominator)
    return EvaluationSummary(
        cases=cases,
        config=config,
        mode=mode,
        provider_successful_cases=provider_cases,
        provider_failed_cases=provider_failed_cases,
        provider_success_rate=_round(provider_cases / cases),
        tool_recall=_round(tool_recall_total / denominator),
        tool_precision=_round(tool_precision_total / denominator),
        exact_tool_set_accuracy=_round(exact_total / denominator),
        workflow_validity_rate=_round(valid_total / denominator),
        workflow_completion_rate=_round(completed_total / denominator),
        hallucinated_tool_rate=unknown_tool_call_rate,
        benchmark_unexpected_tool_rate=benchmark_unexpected_rate,
        unknown_or_disallowed_tool_rate=unknown_tool_call_rate,
        unknown_tool_call_rate=unknown_tool_call_rate,
        cases_with_unknown_tools_rate=cases_with_unknown_tools_rate,
        unknown_or_disallowed_tools_per_case=unknown_or_disallowed_tools_per_case,
        unnecessary_tool_call_rate=_round(unnecessary / total_tool_calls),
        policy_violation_attempt_rate=_round(policy_violations / denominator),
        approval_classification_accuracy=_round(approval_correct / denominator),
        rag_recall_at_k=_round(rag_recall_total / denominator),
        rag_mrr=_round(rag_mrr_total / denominator),
        average_workflow_length=_round(workflow_length_total / denominator),
        execution_success_rate=_round(execution_success_total / denominator),
        end_to_end_workflow_validity_rate=_round(end_to_end_valid_total / cases),
        end_to_end_workflow_completion_rate=_round(end_to_end_completed_total / cases),
        end_to_end_execution_success_rate=_round(end_to_end_execution_success_total / cases),
        planner_latency_ms=_round(planner_latency_total / denominator),
        end_to_end_latency_ms=_round(e2e_latency_total / denominator),
        token_usage=token_total,
        estimated_model_cost_usd=estimated_cost,
    )


def _round(value: float) -> float:
    return round(value, 4)
