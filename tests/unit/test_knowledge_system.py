from __future__ import annotations

from mcp_ops_mcp.knowledge import (
    EngineeringKnowledgeRepository,
    KnowledgeDocument,
    KnowledgeSearchResult,
    seed_documents,
)
from mcp_ops_mcp.services import DiagnosticsDomainService, KnowledgeDomainService
from mcp_ops_simulator.clock import DEFAULT_TEST_TIME
from mcp_ops_simulator.models import FailureScenario
from mcp_ops_simulator.registry import DeviceRegistry


def test_seeded_documents_are_fictional_and_include_required_metadata() -> None:
    documents = seed_documents()

    assert {
        "Simulator Maintenance Manual",
        "Network Troubleshooting Guide",
        "Sensor Troubleshooting Guide",
        "Service Restart Procedure",
        "Simulator Configuration Guide",
        "Preventive Maintenance SOP",
    } == {document.title for document in documents}

    for document in documents:
        payload = document.as_payload()
        assert payload["document_id"]
        assert payload["title"]
        assert payload["document_type"]
        assert payload["version"]
        assert payload["device_model"] == "SIM-ENG-EDGE-1000"
        assert payload["tags"]
        assert payload["created_at"]
        assert payload["updated_at"]
        assert "Fictional/demo engineering documentation" in payload["fictional_notice"]


def test_keyword_search_returns_ranked_metadata_payloads() -> None:
    service = KnowledgeDomainService()

    result = service.search("packet loss timeout", 5)
    documents = result.data["documents"]

    assert result.ok
    assert documents[0]["document_id"] == "kb-network-troubleshooting"
    assert documents[0]["score"] > 0
    assert "content" not in documents[0]
    assert "snippet" in documents[0]


def test_get_document_returns_full_fictional_document() -> None:
    result = KnowledgeDomainService().document("kb-sensor-init")
    document = result.data["document"]

    assert document["document_id"] == "kb-sensor-init"
    assert document["document_type"] == "TROUBLESHOOTING_GUIDE"
    assert document["sections"]
    assert "E-SENSOR-INIT" in document["troubleshooting_steps"]


def test_get_procedure_returns_steps() -> None:
    result = KnowledgeDomainService().procedure("kb-service-restart")
    procedure = result.data["procedure"]

    assert procedure["document_id"] == "kb-service-restart"
    assert procedure["procedure_steps"]
    assert "approval" in " ".join(procedure["procedure_steps"]).lower()


def test_find_troubleshooting_steps_returns_citations() -> None:
    result = KnowledgeDomainService().troubleshooting(
        "E-SENSOR-INIT",
        "SIM-ENG-EDGE-1000",
    )

    assert result.data["steps"]
    assert result.data["references"][0]["document_id"] == "kb-sensor-init"
    assert result.data["references"][0]["citation"].startswith("kb-sensor-init@")


def test_configuration_guides_are_type_filtered() -> None:
    result = KnowledgeDomainService().configuration_guides("configuration telemetry", 10)

    assert result.data["documents"]
    assert {
        document["document_type"] for document in result.data["documents"]
    } == {"CONFIGURATION_GUIDE"}


def test_repository_accepts_replaceable_search_backend_without_contract_change() -> None:
    repository = EngineeringKnowledgeRepository(search_backend=FirstDocumentSearchBackend())

    results = repository.search("anything", limit=1)

    assert results[0].document.document_id == "kb-simulator-maintenance-manual"


def test_diagnostic_summary_includes_knowledge_references() -> None:
    registry = DeviceRegistry.seeded(base_time=DEFAULT_TEST_TIME)
    registry.activate_scenario(
        "SIM-014",
        FailureScenario.NETWORK_TIMEOUT,
        DEFAULT_TEST_TIME,
    )
    service = DiagnosticsDomainService()
    service.device_service.registry = registry

    result = service.summary("SIM-014")
    references = result.data["diagnostic_report"]["references"]

    assert references
    assert references[0]["document_id"] == "kb-network-troubleshooting"
    assert references[0]["citation"].startswith("kb-network-troubleshooting@")


class FirstDocumentSearchBackend:
    def search(
        self,
        documents: list[KnowledgeDocument],
        query: str,
        *,
        document_type: str | None = None,
        limit: int = 10,
    ) -> list[KnowledgeSearchResult]:
        del query, document_type, limit
        return [KnowledgeSearchResult(document=documents[0], score=1)]
