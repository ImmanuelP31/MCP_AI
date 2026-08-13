from __future__ import annotations

from typing import Any

import pytest
from mcp_ops_ai_agent.tool_discovery import ToolDiscoveryService, evaluate_tool_discovery
from mcp_ops_ai_agent.tool_discovery.embeddings import (
    EmbeddingProviderUnavailable,
    FallbackEmbeddingProvider,
    GeminiEmbeddingProvider,
    HashingEmbeddingProvider,
    embedding_provider_from_settings,
)
from mcp_ops_ai_agent.tool_discovery.index import (
    OpenSearchToolEmbeddingIndex,
    SemanticMatch,
    ToolIndexUnavailable,
)
from mcp_ops_ai_agent.tool_discovery.models import ToolDiscoveryFilters, ToolDocument
from mcp_ops_ai_agent.tool_discovery.retrieval import lexical_score
from mcp_ops_ai_agent.tool_discovery.service import ToolMetadataError
from mcp_ops_common.config import Settings
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


class UnavailableEmbeddingProvider:
    def embed(self, text: str) -> tuple[float, ...]:
        del text
        raise EmbeddingProviderUnavailable("provider unavailable")


def test_real_embedding_provider_can_fall_back_to_hashing() -> None:
    provider = FallbackEmbeddingProvider(UnavailableEmbeddingProvider(), HashingEmbeddingProvider())

    vector = provider.embed("failed build logs")

    assert vector
    assert provider.fallback_count == 1


class FakeGeminiEmbeddingProvider(GeminiEmbeddingProvider):
    def __init__(self) -> None:
        super().__init__(api_key="gemini-test-key", model="gemini-embedding-test")

    def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, Any]:
        assert path == "/v1beta/models/gemini-embedding-test:embedContent"
        assert payload["model"] == "models/gemini-embedding-test"
        return {"embedding": {"values": [3.0, 4.0]}}


def test_gemini_embedding_provider_parses_and_normalizes_values() -> None:
    vector = FakeGeminiEmbeddingProvider().embed("failed build logs")

    assert vector == (0.6, 0.8)


def test_embedding_provider_from_settings_supports_gemini_with_hashing_fallback() -> None:
    provider = embedding_provider_from_settings(
        Settings(
            embedding_provider="gemini",
            gemini_api_key="",
            gemini_embedding_model="gemini-embedding-test",
        )
    )

    vector = provider.embed("failed build logs")

    assert vector


def test_embedding_provider_from_settings_can_disable_fallback_for_real_evaluation() -> None:
    provider = embedding_provider_from_settings(
        Settings(
            embedding_provider="gemini",
            gemini_api_key="",
            gemini_embedding_model="gemini-embedding-test",
        ),
        allow_fallback=False,
    )

    with pytest.raises(EmbeddingProviderUnavailable):
        provider.embed("failed build logs")


class FakeOpenSearchToolIndex(OpenSearchToolEmbeddingIndex):
    def __init__(self) -> None:
        super().__init__("http://opensearch:9200")
        self.indexed: list[str] = []

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        if method == "PUT":
            assert body is not None
            self.indexed.append(str(body["name"]))
            return {"result": "created"}
        assert path.endswith("/_search")
        return {
            "hits": {
                "hits": [
                    {"_score": 3.0, "_source": {"name": "get_pipeline_logs"}},
                    {"_score": 1.5, "_source": {"name": "get_build_status"}},
                ]
            }
        }


def test_opensearch_tool_index_indexes_and_searches_documents() -> None:
    index = FakeOpenSearchToolIndex()
    service = ToolDiscoveryService(index=index)

    response = service.retrieve("failed build logs", top_k=2)

    assert "get_pipeline_logs" in index.indexed
    assert [result.tool.name for result in response.ranked_tools][:2] == [
        "get_pipeline_logs",
        "get_build_status",
    ]


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
