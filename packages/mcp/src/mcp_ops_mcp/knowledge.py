from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

FICTIONAL_NOTICE = (
    "Fictional/demo engineering documentation for the simulator environment. "
    "Not actual company documentation."
)


@dataclass(frozen=True, slots=True)
class KnowledgeSection:
    section_id: str
    heading: str
    body: str

    def as_payload(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    document_id: str
    title: str
    document_type: str
    version: str
    device_model: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    sections: list[KnowledgeSection]
    procedure_steps: list[str]
    troubleshooting_steps: dict[str, list[str]]
    signal_references: list[str]

    @property
    def content(self) -> str:
        return "\n".join(section.body for section in self.sections)

    def as_payload(self) -> dict[str, Any]:
        return {
            **self.metadata_payload(),
            "fictional_notice": FICTIONAL_NOTICE,
            "content": self.content,
            "sections": [section.as_payload() for section in self.sections],
            "procedure_steps": self.procedure_steps,
            "troubleshooting_steps": self.troubleshooting_steps,
        }

    def summary_payload(self, score: int | None = None) -> dict[str, Any]:
        payload = {
            **self.metadata_payload(),
            "fictional_notice": FICTIONAL_NOTICE,
            "snippet": self.content[:220],
        }
        if score is not None:
            payload["score"] = score
        return payload

    def metadata_payload(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "document_type": self.document_type,
            "version": self.version,
            "device_model": self.device_model,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class KnowledgeSearchResult:
    document: KnowledgeDocument
    score: int


class KnowledgeSearchBackend(Protocol):
    def search(
        self,
        documents: list[KnowledgeDocument],
        query: str,
        *,
        document_type: str | None = None,
        limit: int = 10,
    ) -> list[KnowledgeSearchResult]:
        """Search implementation boundary; vector search can replace this later."""


class KeywordKnowledgeSearchBackend:
    def search(
        self,
        documents: list[KnowledgeDocument],
        query: str,
        *,
        document_type: str | None = None,
        limit: int = 10,
    ) -> list[KnowledgeSearchResult]:
        terms = _terms(query)
        matches: list[KnowledgeSearchResult] = []
        for document in documents:
            if document_type and document.document_type != document_type:
                continue
            haystack = _search_text(document)
            score = sum(haystack.count(term) for term in terms)
            if score > 0:
                matches.append(KnowledgeSearchResult(document=document, score=score))
        return sorted(matches, key=lambda item: (-item.score, item.document.title))[:limit]


class EngineeringKnowledgeRepository:
    def __init__(
        self,
        documents: list[KnowledgeDocument] | None = None,
        search_backend: KnowledgeSearchBackend | None = None,
    ) -> None:
        self._documents = {doc.document_id: doc for doc in documents or seed_documents()}
        self._search_backend = search_backend or KeywordKnowledgeSearchBackend()

    def search(
        self,
        query: str,
        *,
        limit: int,
        document_type: str | None = None,
    ) -> list[KnowledgeSearchResult]:
        return self._search_backend.search(
            list(self._documents.values()),
            query,
            document_type=document_type,
            limit=limit,
        )

    def get(self, document_id: str) -> KnowledgeDocument | None:
        return self._documents.get(document_id)

    def get_procedure(self, procedure_id: str) -> KnowledgeDocument | None:
        document = self.get(procedure_id)
        if document and document.procedure_steps:
            return document
        return None

    def troubleshooting_steps(
        self,
        error_code: str,
        device_model: str | None,
    ) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        for document in self._documents.values():
            steps = document.troubleshooting_steps.get(error_code)
            if not steps:
                continue
            if document.device_model and device_model and document.device_model != device_model:
                continue
            matches.append(
                {
                    "document_id": document.document_id,
                    "title": document.title,
                    "document_type": document.document_type,
                    "version": document.version,
                    "device_model": document.device_model,
                    "steps": steps,
                    "citation": _citation(document, "troubleshooting"),
                }
            )
        return matches

    def references_for_signals(self, signals: set[str]) -> list[dict[str, Any]]:
        references: list[dict[str, Any]] = []
        for document in self._documents.values():
            matched = sorted(signals & set(document.signal_references))
            if not matched:
                continue
            references.append(
                {
                    "document_id": document.document_id,
                    "title": document.title,
                    "document_type": document.document_type,
                    "version": document.version,
                    "section": document.sections[0].heading,
                    "matched_signals": matched,
                    "citation": _citation(document, document.sections[0].section_id),
                }
            )
        return sorted(references, key=lambda item: str(item["document_id"]))


def seed_documents() -> list[KnowledgeDocument]:
    created = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)
    updated = datetime(2026, 7, 10, 14, 30, tzinfo=UTC)
    return [
        KnowledgeDocument(
            document_id="kb-simulator-maintenance-manual",
            title="Simulator Maintenance Manual",
            document_type="MANUAL",
            version="1.0-demo",
            device_model="SIM-ENG-EDGE-1000",
            tags=["simulator", "maintenance", "telemetry", "health"],
            created_at=created,
            updated_at=updated,
            sections=[
                KnowledgeSection(
                    "overview",
                    "Maintenance Scope",
                    (
                        "This fictional manual describes routine inspection of deterministic "
                        "SIM devices, telemetry publishers, service supervisors, and health "
                        "status calculations."
                    ),
                ),
                KnowledgeSection(
                    "daily-checks",
                    "Daily Checks",
                    (
                        "Review CPU, memory, temperature, disk usage, network latency, packet "
                        "loss, service state, and uptime before demo operations."
                    ),
                ),
            ],
            procedure_steps=[],
            troubleshooting_steps={},
            signal_references=["cpu_percent", "memory_percent", "temperature_c"],
        ),
        KnowledgeDocument(
            document_id="kb-network-troubleshooting",
            title="Network Troubleshooting Guide",
            document_type="TROUBLESHOOTING_GUIDE",
            version="1.0-demo",
            device_model="SIM-ENG-EDGE-1000",
            tags=["network", "packet_loss", "timeout", "E-NET-TIMEOUT"],
            created_at=created,
            updated_at=updated,
            sections=[
                KnowledgeSection(
                    "network-timeout",
                    "Network Timeout Correlation",
                    (
                        "For demo diagnostics, packet loss above threshold together with "
                        "E-NET-TIMEOUT indicates a network communication issue."
                    ),
                ),
                KnowledgeSection(
                    "triage",
                    "Triage Path",
                    (
                        "Compare telemetry latency, packet loss, and telemetry-agent service "
                        "state before requesting an operational change."
                    ),
                ),
            ],
            procedure_steps=[],
            troubleshooting_steps={
                "E-NET-TIMEOUT": [
                    "Collect telemetry for latency and packet loss.",
                    "Confirm telemetry-agent service state.",
                    "Open an incident when timeout and packet loss are both present.",
                ]
            },
            signal_references=["packet_loss", "network_timeout_error", "degraded_service"],
        ),
        KnowledgeDocument(
            document_id="kb-sensor-init",
            title="Sensor Troubleshooting Guide",
            document_type="TROUBLESHOOTING_GUIDE",
            version="1.0-demo",
            device_model="SIM-ENG-EDGE-1000",
            tags=["sensor", "E-SENSOR-INIT", "SIM-014", "sensor_initialization_error"],
            created_at=created,
            updated_at=updated,
            sections=[
                KnowledgeSection(
                    "sensor-init",
                    "Sensor Initialization Failure",
                    (
                        "This fictional guide covers simulator sensor initialization failures "
                        "where sensor bus readiness or sensor-ingestor startup fails."
                    ),
                )
            ],
            procedure_steps=[],
            troubleshooting_steps={
                "E-SENSOR-INIT": [
                    "Validate sensor bus readiness in recent logs.",
                    "Check sensor-ingestor state and crash evidence.",
                    "Use the governed service restart procedure when restart is required.",
                ]
            },
            signal_references=["sensor_initialization_error", "crashed_service", "crash_log"],
        ),
        KnowledgeDocument(
            document_id="kb-service-restart",
            title="Service Restart Procedure",
            document_type="PROCEDURE",
            version="1.0-demo",
            device_model="SIM-ENG-EDGE-1000",
            tags=["restart_service", "approval", "operations", "service crash"],
            created_at=created,
            updated_at=updated,
            sections=[
                KnowledgeSection(
                    "restart-governance",
                    "Governed Restart",
                    (
                        "Service restarts in this fictional environment require gateway policy "
                        "evaluation, human approval for high-risk operations, execution, and "
                        "audit verification."
                    ),
                )
            ],
            procedure_steps=[
                "Open a restart_service request through the MCP gateway.",
                "Wait for PENDING approval state.",
                "Have an authorized human approve the request.",
                "Execute the approved operation once.",
                "Verify service state and audit event.",
            ],
            troubleshooting_steps={},
            signal_references=["crashed_service", "crash_log"],
        ),
        KnowledgeDocument(
            document_id="kb-configuration-guide",
            title="Simulator Configuration Guide",
            document_type="CONFIGURATION_GUIDE",
            version="1.0-demo",
            device_model="SIM-ENG-EDGE-1000",
            tags=["configuration", "firmware", "telemetry", "disk"],
            created_at=created,
            updated_at=updated,
            sections=[
                KnowledgeSection(
                    "config-control",
                    "Configuration Control",
                    (
                        "Configuration changes require policy checks, approved intent, bounded "
                        "patches, and audit capture. Arbitrary SQL, files, and shell commands "
                        "are outside the supported contract."
                    ),
                )
            ],
            procedure_steps=[
                "Review the proposed bounded configuration patch.",
                "Submit update_device_configuration through the gateway.",
                "Capture approval and resulting configuration in audit history.",
            ],
            troubleshooting_steps={
                "E-DISK-CAPACITY": [
                    "Check disk usage telemetry.",
                    "Review retained diagnostic artifacts.",
                    "Apply cleanup or allocation changes through governed configuration.",
                ]
            },
            signal_references=["disk_percent", "telemetry_delay"],
        ),
        KnowledgeDocument(
            document_id="kb-preventive-maintenance-sop",
            title="Preventive Maintenance SOP",
            document_type="SOP",
            version="1.0-demo",
            device_model="SIM-ENG-EDGE-1000",
            tags=["preventive", "maintenance", "cpu", "memory", "disk"],
            created_at=created,
            updated_at=updated,
            sections=[
                KnowledgeSection(
                    "weekly-review",
                    "Weekly Review",
                    (
                        "Review simulator resource trends, repeated diagnostics, open tickets, "
                        "and unresolved alerts before planned demo windows."
                    ),
                )
            ],
            procedure_steps=[
                "Review fleet health and recent diagnostic reports.",
                "Identify devices with recurring CPU, memory, or disk pressure.",
                "Create tickets for repeated threshold warnings.",
                "Confirm no unauthorized high-risk operation occurred.",
            ],
            troubleshooting_steps={
                "E-CPU-LATENCY": [
                    "Review CPU telemetry and diagnostic-runner logs.",
                    "Compare latency with historical CPU saturation incidents.",
                    "Reduce simulator load before restarting services.",
                ],
                "E-MEM-PRESSURE": [
                    "Capture process memory usage.",
                    "Check for repeated memory pressure alerts.",
                    "Plan maintenance rather than immediate restart unless impact is active.",
                ],
            },
            signal_references=["cpu_percent", "process_latency_error", "memory_percent"],
        ),
    ]


def _terms(query: str) -> list[str]:
    return [term.lower() for term in re.findall(r"[a-zA-Z0-9_-]+", query) if len(term) >= 2]


def _search_text(document: KnowledgeDocument) -> str:
    return " ".join(
        [
            document.title,
            document.document_type,
            document.device_model or "",
            " ".join(document.tags),
            document.content,
            " ".join(document.procedure_steps),
            " ".join(step for steps in document.troubleshooting_steps.values() for step in steps),
        ]
    ).lower()


def _citation(document: KnowledgeDocument, section_id: str) -> str:
    return f"{document.document_id}@{document.version}#{section_id}"
