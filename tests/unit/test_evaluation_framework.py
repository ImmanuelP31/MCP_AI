from __future__ import annotations

import json
from pathlib import Path

from evaluation.datasets import generate_benchmark_items
from evaluation.metrics import (
    MetricInputs,
    compute_summary,
    exact_tool_set_accuracy,
    mean_reciprocal_rank,
    precision,
    recall,
)
from evaluation.runner import run_evaluation, run_execution_benchmark
from evaluation.runner.execution import execution_benchmark_items
from evaluation.scenarios import config_by_name


def test_synthetic_dataset_contains_at_least_300_enterprise_engineering_tasks() -> None:
    items = generate_benchmark_items()

    assert len(items) >= 300
    categories = {item.category for item in items}
    assert "build investigation" in categories
    assert "production approval" in categories
    assert "multi-tool workflows" in categories
    assert all(item.expected_tools for item in items)
    assert all(isinstance(item.relevant_documents, list) for item in items)


def test_heldout_adversarial_dataset_contains_independent_eval_cases() -> None:
    dataset_path = (
        Path(__file__).resolve().parents[2]
        / "evaluation"
        / "datasets"
        / "heldout_adversarial_engineering_tasks.json"
    )
    items = json.loads(dataset_path.read_text(encoding="utf-8"))

    assert len(items) == 50
    assert {item["id"] for item in items} == {f"HELDOUT-{index:03d}" for index in range(1, 51)}
    assert any("Ignore the approval policy" in item["request"] for item in items)
    assert any("forgot which repository" in item["request"] for item in items)
    assert all(isinstance(item["expected_tools"], list) for item in items)
    assert all(isinstance(item["prohibited_tools"], list) for item in items)
    assert all(isinstance(item["relevant_documents"], list) for item in items)


def test_heldout_adversarial_dataset_can_be_selected_by_runner() -> None:
    result = run_evaluation(
        selected_configs=(config_by_name("semantic_rag_graph"),),
        dataset_name="heldout_adversarial",
        limit=2,
        output=False,
    )

    assert len(result.cases) == 2
    assert result.cases[0]["id"] == "HELDOUT-001"
    assert result.cases[0]["category"] == "heldout adversarial"
    assert result.provider_evaluation == "planner_quality"
    assert result.pace_seconds == 0.0


def test_runner_records_circuit_breaker_evaluation_mode() -> None:
    result = run_evaluation(
        selected_configs=(config_by_name("semantic_rag_graph"),),
        dataset_name="heldout_adversarial",
        limit=1,
        output=False,
        provider_evaluation="circuit_breaker",
        pace_seconds=0.25,
    )

    assert result.provider_evaluation == "circuit_breaker"
    assert result.pace_seconds == 0.25


def test_precision_recall_exact_accuracy_and_mrr_are_computed() -> None:
    expected = {"get_build_status", "get_pipeline_logs"}
    actual = {"get_build_status", "create_ticket"}

    assert recall(expected, actual) == 0.5
    assert precision(expected | {"create_ticket"}, ["get_build_status", "create_ticket"]) == 1.0
    assert precision(expected, [], expected) == 0.0
    assert precision(set(), [], set()) == 1.0
    assert exact_tool_set_accuracy(expected, actual) == 0.0
    assert mean_reciprocal_rank({"DOC-2"}, ["DOC-1", "DOC-2"]) == 0.5


def test_summary_metrics_capture_policy_approval_rag_and_latency() -> None:
    summary = compute_summary(
        config="semantic_rag_graph",
        mode="mock",
        inputs=[
            MetricInputs(
                expected_tools=["get_build_status", "run_tests"],
                acceptable_tools=["get_deployment_status"],
                actual_tools=["get_build_status", "run_tests", "get_deployment_status"],
                prohibited_tools=["delete_bad_deployment"],
                required_approvals=["deploy_staging"],
                actual_approvals=["deploy_staging"],
                relevant_documents=["ENG-POLICY-14"],
                retrieved_documents=["PAYMENTS-DEPLOY-03", "ENG-POLICY-14"],
                workflow_valid=True,
                workflow_completed=True,
                execution_succeeded=True,
                planner_latency_ms=10.0,
                end_to_end_latency_ms=20.0,
                token_usage=0,
                estimated_cost_usd=None,
            ),
            MetricInputs(
                expected_tools=["get_service_owner"],
                acceptable_tools=[],
                actual_tools=["get_service_owner", "restart_service"],
                prohibited_tools=["restart_service"],
                required_approvals=[],
                actual_approvals=["restart_service"],
                relevant_documents=["OWNERSHIP-01"],
                retrieved_documents=[],
                workflow_valid=False,
                workflow_completed=False,
                execution_succeeded=False,
                planner_latency_ms=30.0,
                end_to_end_latency_ms=40.0,
                token_usage=0,
                estimated_cost_usd=None,
            ),
        ],
    )

    assert summary.cases == 2
    assert summary.workflow_validity_rate == 0.5
    assert summary.plan_acceptance_rate == 0.5
    assert summary.approval_classification_accuracy == 0.5
    assert summary.policy_violation_attempt_rate == 0.5
    assert summary.rag_mrr == 0.25
    assert summary.planner_latency_ms == 20.0


def test_summary_metrics_separate_provider_availability_from_planner_quality() -> None:
    summary = compute_summary(
        config="semantic_rag_graph",
        mode="real",
        inputs=[
            MetricInputs(
                expected_tools=["get_build_status"],
                acceptable_tools=[],
                actual_tools=["get_build_status"],
                prohibited_tools=[],
                required_approvals=[],
                actual_approvals=[],
                relevant_documents=[],
                retrieved_documents=[],
                workflow_valid=True,
                workflow_completed=True,
                execution_succeeded=True,
                planner_latency_ms=10.0,
                end_to_end_latency_ms=12.0,
                token_usage=10,
                estimated_cost_usd=0.01,
                provider_success=True,
            ),
            MetricInputs(
                expected_tools=["run_tests"],
                acceptable_tools=[],
                actual_tools=[],
                prohibited_tools=[],
                required_approvals=["deploy_staging"],
                actual_approvals=[],
                relevant_documents=[],
                retrieved_documents=[],
                workflow_valid=False,
                workflow_completed=False,
                execution_succeeded=False,
                planner_latency_ms=0.0,
                end_to_end_latency_ms=0.0,
                token_usage=0,
                estimated_cost_usd=None,
                provider_success=False,
            ),
        ],
    )

    assert summary.cases == 2
    assert summary.provider_successful_cases == 1
    assert summary.provider_failed_cases == 1
    assert summary.provider_success_rate == 0.5
    assert summary.tool_precision == 1.0
    assert summary.approval_classification_accuracy == 1.0
    assert summary.workflow_validity_rate == 1.0
    assert summary.end_to_end_workflow_validity_rate == 0.5
    assert summary.execution_success_rate == 1.0


def test_unknown_tool_metrics_distinguish_call_rate_from_case_rate() -> None:
    summary = compute_summary(
        config="semantic_rag_graph",
        mode="real",
        inputs=[
            MetricInputs(
                expected_tools=["get_build_status"],
                acceptable_tools=[],
                actual_tools=["get_build_status"],
                prohibited_tools=[],
                required_approvals=[],
                actual_approvals=[],
                relevant_documents=[],
                retrieved_documents=[],
                workflow_valid=False,
                workflow_completed=False,
                execution_succeeded=False,
                planner_latency_ms=10.0,
                end_to_end_latency_ms=12.0,
                token_usage=10,
                estimated_cost_usd=0.01,
                provider_success=True,
                unknown_or_disallowed_tools=2,
            )
        ],
    )

    assert summary.unknown_tool_call_rate == 0.6667
    assert summary.unknown_or_disallowed_tool_rate == 0.6667
    assert summary.cases_with_unknown_tools_rate == 1.0
    assert summary.unknown_or_disallowed_tools_per_case == 2.0


def test_execution_benchmark_covers_policy_approval_retry_and_compensation() -> None:
    items = execution_benchmark_items()

    assert len(items) >= 5
    assert any(item.required_approvals for item in items)
    assert any(item.expected_retried_tools for item in items)
    assert any(item.expected_compensated_tools for item in items)


def test_execution_benchmark_runs_mcp_tools_and_checks_final_state() -> None:
    result = run_execution_benchmark(output=False)

    assert result.summary["cases"] == 5
    assert result.summary["planning_success_rate"] == 1.0
    assert result.summary["policy_correctness_rate"] == 1.0
    assert result.summary["approval_correctness_rate"] == 1.0
    assert result.summary["execution_success_rate"] == 1.0
    assert result.summary["retry_recovery_rate"] == 1.0
    assert result.summary["compensation_success_rate"] == 1.0
    assert result.summary["final_state_correctness_rate"] == 1.0
    assert any(case["tool_attempts"].get("run_tests") == 2 for case in result.cases)
