from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from mcp_ops_simulator.ids import deterministic_uuid
from mcp_ops_simulator.models import DeviceTelemetry, ServiceState, SimulatedDevice


@dataclass(frozen=True, slots=True)
class DiagnosticEvidence:
    signal: str
    value: str | int | float | bool
    threshold: str | int | float | bool | None
    matched: bool
    detail: str

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DiagnosticTimelineEvent:
    timestamp: datetime
    event_type: str
    detail: str

    def as_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.isoformat()
        return payload


@dataclass(frozen=True, slots=True)
class RelatedIncident:
    incident_id: str
    title: str
    matched_signals: list[str]
    similarity: float

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DiagnosticReference:
    document_id: str
    title: str
    document_type: str
    version: str
    section: str
    matched_signals: list[str]
    citation: str

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    diagnostic_id: str
    device_id: str
    timestamp: datetime
    severity: str
    observations: list[str]
    evidence: list[DiagnosticEvidence]
    possible_causes: list[str]
    recommended_actions: list[str]
    confidence: float
    related_incidents: list[RelatedIncident]
    references: list[DiagnosticReference]
    timeline: list[DiagnosticTimelineEvent]

    def as_payload(self) -> dict[str, Any]:
        return {
            "diagnostic_id": self.diagnostic_id,
            "device_id": self.device_id,
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity,
            "observations": self.observations,
            "evidence": [item.as_payload() for item in self.evidence],
            "possible_causes": self.possible_causes,
            "recommended_actions": self.recommended_actions,
            "confidence": self.confidence,
            "related_incidents": [incident.as_payload() for incident in self.related_incidents],
            "references": [reference.as_payload() for reference in self.references],
            "timeline": [event.as_payload() for event in self.timeline],
        }


class RuleBasedDiagnosticsEngine:
    """Deterministic diagnostics correlation, not ML-based root-cause analysis."""

    def diagnose(
        self,
        device: SimulatedDevice,
        telemetry: DeviceTelemetry,
        recent_errors: list[dict[str, Any]],
        historical_incidents: list[dict[str, Any]],
        knowledge_references: list[dict[str, Any]] | None = None,
    ) -> DiagnosticReport:
        evidence = _collect_evidence(device, telemetry, recent_errors)
        observations = [item.detail for item in evidence if item.matched]
        possible_causes: list[str] = []
        recommended_actions: list[str] = []
        matched_signals = {item.signal for item in evidence if item.matched}

        if {"packet_loss", "network_timeout_error"}.issubset(matched_signals):
            possible_causes.append("network communication issue")
            recommended_actions.append("Inspect network path and telemetry-agent connectivity.")
        if "cpu_percent" in matched_signals and (
            "high_latency" in matched_signals or "process_latency_error" in matched_signals
        ):
            possible_causes.append("CPU saturation candidate")
            recommended_actions.append(
                "Review CPU-bound simulator processes and diagnostic-runner load."
            )
        if {"crashed_service", "crash_log"}.issubset(matched_signals):
            possible_causes.append("service failure candidate")
            recommended_actions.append(
                "Follow governed service restart procedure for the affected service."
            )
        if "memory_percent" in matched_signals:
            possible_causes.append("memory pressure candidate")
            recommended_actions.append(
                "Capture heap/process memory profile and restart only after approval."
            )
        if "telemetry_delay" in matched_signals:
            possible_causes.append("telemetry delay")
            recommended_actions.append("Verify telemetry scheduler and Kafka publish latency.")
        if "disk_percent" in matched_signals:
            possible_causes.append("disk capacity warning")
            recommended_actions.append(
                "Clear old diagnostic artifacts or increase simulator disk allocation."
            )
        if "sensor_initialization_error" in matched_signals:
            possible_causes.append("sensor initialization failure")
            recommended_actions.append("Run sensor initialization SOP before restart_service.")

        if not possible_causes:
            possible_causes.append("no deterministic failure rule matched")
            recommended_actions.append(
                "Collect additional telemetry and logs before operating the device."
            )

        severity = _severity(evidence)
        related = _related_incidents(historical_incidents, matched_signals)
        references = _references(knowledge_references or [], matched_signals)
        timeline = _timeline(device, telemetry, recent_errors, evidence)
        confidence = _confidence(evidence, related)

        return DiagnosticReport(
            diagnostic_id=str(
                deterministic_uuid(f"diagnostic:{device.device_id}:{telemetry.timestamp.isoformat()}")
            ),
            device_id=device.device_id,
            timestamp=telemetry.timestamp,
            severity=severity,
            observations=observations,
            evidence=evidence,
            possible_causes=possible_causes,
            recommended_actions=_dedupe(recommended_actions),
            confidence=confidence,
            related_incidents=related,
            references=references,
            timeline=timeline,
        )


class SignalSimilarityIncidentRetriever:
    """Retrieve related incidents using weighted structured diagnostic signals."""

    def retrieve(
        self,
        incidents: list[dict[str, Any]],
        matched_signals: set[str],
    ) -> list[RelatedIncident]:
        expanded_signals = _expand_signals(matched_signals)
        related: list[RelatedIncident] = []
        for incident in incidents:
            incident_signals = set(str(signal) for signal in incident.get("signals", []))
            expanded_incident_signals = _expand_signals(incident_signals)
            overlap = sorted(matched_signals & incident_signals)
            semantic_overlap = expanded_signals & expanded_incident_signals
            similarity = _signal_similarity(
                expanded_signals,
                expanded_incident_signals,
                semantic_overlap,
            )
            if similarity <= 0:
                continue
            related.append(
                RelatedIncident(
                    incident_id=str(incident["incident_id"]),
                    title=str(incident["title"]),
                    matched_signals=sorted(set(overlap) | semantic_overlap),
                    similarity=similarity,
                )
            )
        return sorted(related, key=lambda item: item.similarity, reverse=True)


def _collect_evidence(
    device: SimulatedDevice,
    telemetry: DeviceTelemetry,
    recent_errors: list[dict[str, Any]],
) -> list[DiagnosticEvidence]:
    service_states = telemetry.service_states
    error_codes = {str(error.get("error_code")) for error in recent_errors}
    messages = " ".join(str(error.get("message", "")).lower() for error in recent_errors)
    crashed_services = [
        name for name, state in service_states.items() if state == ServiceState.CRASHED
    ]
    degraded_services = [
        name for name, state in service_states.items() if state == ServiceState.DEGRADED
    ]
    return [
        DiagnosticEvidence(
            "packet_loss",
            telemetry.packet_loss_percent,
            10.0,
            telemetry.packet_loss_percent > 10.0,
            f"Packet loss is {telemetry.packet_loss_percent}%.",
        ),
        DiagnosticEvidence(
            "network_timeout_error",
            "E-NET-TIMEOUT" in error_codes,
            True,
            "E-NET-TIMEOUT" in error_codes or "timeout" in messages,
            "Recent errors include network timeout evidence.",
        ),
        DiagnosticEvidence(
            "cpu_percent",
            telemetry.cpu_percent,
            90.0,
            telemetry.cpu_percent > 90.0,
            f"CPU usage is {telemetry.cpu_percent}%.",
        ),
        DiagnosticEvidence(
            "high_latency",
            telemetry.network_latency_ms,
            250.0,
            telemetry.network_latency_ms > 250.0,
            f"Network/process response latency is {telemetry.network_latency_ms}ms.",
        ),
        DiagnosticEvidence(
            "process_latency_error",
            "E-CPU-LATENCY" in error_codes,
            True,
            "E-CPU-LATENCY" in error_codes or "response latency" in messages,
            "Recent errors include process response latency evidence.",
        ),
        DiagnosticEvidence(
            "memory_percent",
            telemetry.memory_percent,
            90.0,
            telemetry.memory_percent > 90.0,
            f"Memory usage is {telemetry.memory_percent}%.",
        ),
        DiagnosticEvidence(
            "crashed_service",
            ",".join(crashed_services),
            "no crashed services",
            bool(crashed_services),
            f"Crashed services: {', '.join(crashed_services) or 'none'}.",
        ),
        DiagnosticEvidence(
            "degraded_service",
            ",".join(degraded_services),
            "no degraded services",
            bool(degraded_services),
            f"Degraded services: {', '.join(degraded_services) or 'none'}.",
        ),
        DiagnosticEvidence(
            "crash_log",
            "crash" in messages,
            True,
            "crash" in messages,
            "Recent logs include crash evidence.",
        ),
        DiagnosticEvidence(
            "sensor_initialization_error",
            "E-SENSOR-INIT" in error_codes,
            True,
            "E-SENSOR-INIT" in error_codes,
            "Recent errors include sensor initialization failure.",
        ),
        DiagnosticEvidence(
            "telemetry_delay",
            telemetry.delayed,
            False,
            telemetry.delayed,
            "Telemetry timestamp is delayed beyond expected interval.",
        ),
        DiagnosticEvidence(
            "disk_percent",
            telemetry.disk_percent,
            85.0,
            telemetry.disk_percent > 85.0,
            f"Disk usage is {telemetry.disk_percent}%.",
        ),
        DiagnosticEvidence(
            "temperature_c",
            telemetry.temperature_c,
            80.0,
            telemetry.temperature_c > 80.0,
            f"Temperature is {telemetry.temperature_c}C.",
        ),
        DiagnosticEvidence(
            "device_active_scenario",
            device.active_scenario.value if device.active_scenario else "none",
            None,
            device.active_scenario is not None,
            "Simulator scenario is "
            f"{device.active_scenario.value if device.active_scenario else 'none'}.",
        ),
    ]


def _severity(evidence: list[DiagnosticEvidence]) -> str:
    matched = {item.signal for item in evidence if item.matched}
    if {"packet_loss", "network_timeout_error"}.issubset(matched):
        return "CRITICAL"
    if "crashed_service" in matched or "cpu_percent" in matched or "temperature_c" in matched:
        return "CRITICAL"
    if {
        "memory_percent",
        "disk_percent",
        "telemetry_delay",
        "degraded_service",
        "crash_log",
        "sensor_initialization_error",
    } & matched:
        return "WARNING"
    return "INFO"


def _related_incidents(
    incidents: list[dict[str, Any]],
    matched_signals: set[str],
) -> list[RelatedIncident]:
    return SignalSimilarityIncidentRetriever().retrieve(incidents, matched_signals)


SIGNAL_GROUPS: dict[str, set[str]] = {
    "network": {"packet_loss", "network_timeout_error", "high_latency", "degraded_service"},
    "compute": {"cpu_percent", "process_latency_error", "memory_percent", "high_latency"},
    "service": {"crashed_service", "crash_log", "sensor_initialization_error"},
    "storage": {"disk_percent", "telemetry_delay"},
}


def _expand_signals(signals: set[str]) -> set[str]:
    expanded = set(signals)
    for group, members in SIGNAL_GROUPS.items():
        if signals & members:
            expanded.add(group)
    return expanded


def _signal_similarity(
    left: set[str],
    right: set[str],
    overlap: set[str],
) -> float:
    if not left or not right or not overlap:
        return 0.0
    union_size = len(left | right)
    group_bonus = 0.15 * len({signal for signal in overlap if signal in SIGNAL_GROUPS})
    return round(min(1.0, len(overlap) / union_size + group_bonus), 2)


def _references(
    references: list[dict[str, Any]],
    matched_signals: set[str],
) -> list[DiagnosticReference]:
    diagnostics_references: list[DiagnosticReference] = []
    for reference in references:
        reference_signals = set(str(signal) for signal in reference.get("matched_signals", []))
        overlap = sorted(reference_signals & matched_signals)
        if not overlap:
            continue
        diagnostics_references.append(
            DiagnosticReference(
                document_id=str(reference["document_id"]),
                title=str(reference["title"]),
                document_type=str(reference["document_type"]),
                version=str(reference["version"]),
                section=str(reference["section"]),
                matched_signals=overlap,
                citation=str(reference["citation"]),
            )
        )
    return diagnostics_references


def _timeline(
    device: SimulatedDevice,
    telemetry: DeviceTelemetry,
    recent_errors: list[dict[str, Any]],
    evidence: list[DiagnosticEvidence],
) -> list[DiagnosticTimelineEvent]:
    events = [
        DiagnosticTimelineEvent(
            device.last_seen,
            "device_identified",
            f"Identified {device.device_id}.",
        ),
        DiagnosticTimelineEvent(
            telemetry.timestamp,
            "telemetry_collected",
            "Collected current simulator telemetry.",
        ),
    ]
    for error in recent_errors:
        events.append(
            DiagnosticTimelineEvent(
                telemetry.timestamp,
                "error_collected",
                f"{error.get('error_code')}: {error.get('message')}",
            )
        )
    for item in evidence:
        if item.matched:
            events.append(DiagnosticTimelineEvent(telemetry.timestamp, "rule_matched", item.signal))
    return sorted(events, key=lambda item: item.timestamp)


def _confidence(evidence: list[DiagnosticEvidence], related: list[RelatedIncident]) -> float:
    matched_count = sum(1 for item in evidence if item.matched)
    confidence = min(0.95, 0.35 + matched_count * 0.07 + len(related) * 0.05)
    return round(confidence, 2)


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped
