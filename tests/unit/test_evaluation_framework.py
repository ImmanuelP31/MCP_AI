from __future__ import annotations

from evaluation.datasets import generate_benchmark_items
from evaluation.metrics import (
    MetricInputs,
    compute_summary,
    exact_tool_set_accuracy,
    mean_reciprocal_rank,
    precision,
    recall,
)


def test_synthetic_dataset_contains_at_least_300_enterprise_engineering_tasks() -> None:
    items = generate_benchmark_items()

    assert len(items) >= 300
    categories = {item.category for item in items}
    assert "build investigation" in categories
    assert "production approval" in categories
    assert "multi-tool workflows" in categories
    assert all(item.expected_tools for item in items)
    assert all(isinstance(item.relevant_documents, list) for item in items)


def test_precision_recall_exact_accuracy_and_mrr_are_computed() -> None:
    expected = {"get_build_status", "get_pipeline_logs"}
    actual = {"get_build_status", "create_ticket"}

    assert recall(expected, actual) == 0.5
    assert precision(expected | {"create_ticket"}, ["get_build_status", "create_ticket"]) == 1.0
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
    assert summary.approval_classification_accuracy == 0.5
    assert summary.policy_violation_attempt_rate == 0.5
    assert summary.rag_mrr == 0.25
    assert summary.planner_latency_ms == 20.0
