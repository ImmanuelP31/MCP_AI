from __future__ import annotations

import pytest
from mcp_ops_ai_agent.tool_discovery import ToolDiscoveryService, evaluate_tool_discovery
from mcp_ops_ai_agent.tool_discovery.index import SemanticMatch, ToolIndexUnavailable
from mcp_ops_ai_agent.tool_discovery.models import ToolDiscoveryFilters, ToolDocument
from mcp_ops_ai_agent.tool_discovery.retrieval import lexical_score
from mcp_ops_ai_agent.tool_discovery.service import ToolMetadataError
from mcp_ops_observability.metrics import metrics_response
from mcp_ops_policy.tool_registry import RiskLevel, ToolMetadata


def test_failed_build_query_retrieves_ci_tools_before_planning() -> None:
    service = ToolDiscoveryService()

    response = service.retrieve("Why did yesterday's production build fail?", top_k=4)
    names = [result.tool.name for result in response.ranked_tools]

    assert names[:4] == [
        "get_latest_failed_build",
        "get_build_status",
        "get_pipeline_logs",
        "get_failed_jobs",
    ]
    assert all(result.authorization_status == "authorized" for result in response.ranked_tools)
    assert response.ranked_tools[0].combined_score >= response.ranked_tools[1].combined_score


def test_lexical_scoring_prefers_matching_tool_terms() -> None:
    service = ToolDiscoveryService()
    documents = {document.name: document for document in service.documents}

    logs = lexical_score("pipeline logs failed build", documents["get_pipeline_logs"])
    restart = lexical_score("pipeline logs failed build", documents["restart_service"])

    assert logs > restart


def test_metadata_filters_limit_allowed_server() -> None:
    service = ToolDiscoveryService()

    response = service.retrieve(
        "Show commit history for the failed deployment.",
        top_k=5,
        allowed_servers={"repository-mcp"},
    )

    assert response.ranked_tools
    assert {result.tool.server for result in response.ranked_tools} == {"repository-mcp"}


def test_policy_filtering_excludes_unauthorized_tools() -> None:
    service = ToolDiscoveryService()

    response = service.retrieve("Restart SIM-014 service.", role="VIEWER", top_k=8)
    names = {result.tool.name for result in response.ranked_tools}

    assert "restart_service" not in names
    assert response.filtered_out_unauthorized >= 1


def test_empty_registry_returns_empty_result() -> None:
    service = ToolDiscoveryService(registry={})

    response = service.retrieve("Why did the build fail?", top_k=5)

    assert response.ranked_tools == []


def test_malformed_tool_metadata_is_rejected() -> None:
    malformed = ToolMetadata.model_construct(
        tool_name="",
        domain="cicd",
        description="Broken metadata.",
        risk_level=RiskLevel.LOW,
        required_permission="cicd:read",
        requires_approval=False,
        server="cicd-mcp",
        category="cicd",
        tags=["build"],
        required_roles=["ENGINEER"],
        executable=False,
        timeout_seconds=5,
        rate_limit="60/minute",
        enabled=True,
    )

    with pytest.raises(ToolMetadataError) as exc_info:
        ToolDiscoveryService(registry={"broken": malformed})

    assert "does not match" in str(exc_info.value) or "malformed" in str(exc_info.value)


class FailingIndex:
    @property
    def backend_name(self) -> str:
        return "opensearch"

    def search(
        self,
        query: str,
        documents: list[ToolDocument],
        *,
        top_k: int,
        filters: ToolDiscoveryFilters,
    ) -> list[SemanticMatch]:
        del query, documents, top_k, filters
        raise ToolIndexUnavailable("OpenSearch unavailable.")


def test_opensearch_failure_falls_back_to_local_retrieval() -> None:
    service = ToolDiscoveryService(index=FailingIndex())

    response = service.retrieve("Find the failed CI job.", top_k=3)

    assert response.index_backend == "fallback:in-memory-hashing"
    assert response.ranked_tools


def test_tool_discovery_emits_prometheus_metrics() -> None:
    service = ToolDiscoveryService()

    service.retrieve("Why did the build fail?", top_k=3)

    metrics = metrics_response().decode("utf-8")
    assert "mcp_tool_discovery_requests_total" in metrics
    assert "mcp_tool_discovery_latency_seconds" in metrics
    assert "mcp_tool_discovery_results_total" in metrics


def test_tool_discovery_benchmark_has_50_cases_and_reports_quality_metrics() -> None:
    result = evaluate_tool_discovery(ToolDiscoveryService(), top_k=5)

    assert result.cases == 50
    assert result.recall_at_k >= 0.6
    assert result.mrr >= 0.7
