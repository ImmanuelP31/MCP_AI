from __future__ import annotations

from dataclasses import dataclass

from mcp_ops_ai_agent.models import AgentIntent, Intent, ToolSelection


@dataclass(frozen=True, slots=True)
class ToolRoute:
    selections: list[ToolSelection]
    route_confidence: float
    escalation_required: bool
    escalation_reason: str | None


class ToolSelectionPolicy:
    """Deterministic agent router for governed tool workflows.

    The policy is intentionally inspectable: it selects only known MCP tools, records why each
    tool was selected, and computes a route confidence used for escalation.
    """

    def route(self, intent: Intent) -> ToolRoute:
        if intent.intent == AgentIntent.ANSWER_QUESTION:
            return _route(
                [
                    ("list_devices", "collect fleet state", 0.88),
                    ("get_open_tickets", "collect active work queue", 0.82),
                    ("search_knowledge", "retrieve relevant engineering context", 0.78),
                ],
                0.82,
                False,
                None,
            )
        if intent.intent == AgentIntent.DIAGNOSE_UNHEALTHY_DEVICE:
            return _route(
                [
                    ("get_device_status", "confirm current device state", 0.95),
                    ("get_device_telemetry", "collect recent telemetry evidence", 0.94),
                    ("get_device_services", "inspect service health", 0.93),
                    ("get_recent_errors", "collect recent error evidence", 0.92),
                    ("find_similar_incidents", "retrieve signal-similar incidents", 0.86),
                    ("run_diagnostic_check", "run bounded diagnostic check", 0.88),
                    ("generate_diagnostic_summary", "aggregate diagnostic evidence", 0.9),
                ],
                0.91,
                False,
                None,
            )
        if intent.intent == AgentIntent.FIND_PROCEDURE:
            return _route(
                [
                    ("find_troubleshooting_steps", "retrieve procedure steps by signal", 0.88),
                    ("search_knowledge", "retrieve supporting source documents", 0.84),
                ],
                0.86,
                False,
                None,
            )
        if intent.intent == AgentIntent.CREATE_TICKET:
            return _route(
                [
                    ("get_device_status", "attach current device state", 0.91),
                    ("get_recent_errors", "attach diagnostic evidence", 0.89),
                    ("create_ticket", "create maintenance work item", 0.92),
                ],
                0.9,
                False,
                None,
            )
        if intent.intent == AgentIntent.REQUEST_SERVICE_RESTART:
            return _route(
                [
                    ("get_recent_errors", "infer affected service from errors", 0.83),
                    ("get_device_services", "confirm affected service state", 0.87),
                    ("restart_service", "request governed service restart", 0.78),
                ],
                0.82,
                True,
                "High-risk operation requires human approval.",
            )
        if intent.intent == AgentIntent.EXECUTE_APPROVED_RESTART:
            return _route(
                [("restart_service", "execute previously approved restart", 0.84)],
                0.84,
                True,
                "Execution requires a valid approved approval ID.",
            )
        return _route([], 0.2, True, "Intent confidence below automation threshold.")


def _route(
    selections: list[tuple[str, str, float]],
    route_confidence: float,
    escalation_required: bool,
    escalation_reason: str | None,
) -> ToolRoute:
    return ToolRoute(
        selections=[
            ToolSelection(tool_name=name, reason=reason, confidence=confidence)
            for name, reason, confidence in selections
        ],
        route_confidence=route_confidence,
        escalation_required=escalation_required,
        escalation_reason=escalation_reason,
    )
