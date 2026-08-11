from __future__ import annotations

from dataclasses import dataclass

from mcp_ops_ai_agent.models import AgentIntent
from mcp_ops_ai_agent.service import AiEngineeringAgent


@dataclass(frozen=True, slots=True)
class AgentBenchmarkCase:
    case_id: str
    prompt: str
    auth_token: str
    expected_intent: AgentIntent
    expected_tools: tuple[str, ...]
    expected_ok: bool
    expected_escalation: bool


@dataclass(frozen=True, slots=True)
class AgentBenchmarkResult:
    cases: int
    intent_accuracy: float
    tool_route_accuracy: float
    outcome_accuracy: float
    escalation_accuracy: float
    hallucinated_tool_calls: int
    tool_failure_rate: float

    def as_payload(self) -> dict[str, float | int]:
        return {
            "cases": self.cases,
            "intent_accuracy": self.intent_accuracy,
            "tool_route_accuracy": self.tool_route_accuracy,
            "outcome_accuracy": self.outcome_accuracy,
            "escalation_accuracy": self.escalation_accuracy,
            "hallucinated_tool_calls": self.hallucinated_tool_calls,
            "tool_failure_rate": self.tool_failure_rate,
        }


DEFAULT_BENCHMARK_CASES: tuple[AgentBenchmarkCase, ...] = (
    AgentBenchmarkCase(
        case_id="diagnose-sim-014",
        prompt="Why is SIM-014 unhealthy?",
        auth_token="engineer-token",  # noqa: S106  # nosec B106
        expected_intent=AgentIntent.DIAGNOSE_UNHEALTHY_DEVICE,
        expected_tools=(
            "get_device_status",
            "get_device_telemetry",
            "get_device_services",
            "get_recent_errors",
            "find_similar_incidents",
            "run_diagnostic_check",
            "generate_diagnostic_summary",
        ),
        expected_ok=True,
        expected_escalation=True,
    ),
    AgentBenchmarkCase(
        case_id="procedure-sim-014",
        prompt="What procedure should I follow for SIM-014?",
        auth_token="viewer-token",  # noqa: S106  # nosec B106
        expected_intent=AgentIntent.FIND_PROCEDURE,
        expected_tools=("find_troubleshooting_steps", "search_knowledge"),
        expected_ok=True,
        expected_escalation=False,
    ),
    AgentBenchmarkCase(
        case_id="ticket-sim-014",
        prompt="Create a maintenance ticket for SIM-014.",
        auth_token="engineer-token",  # noqa: S106  # nosec B106
        expected_intent=AgentIntent.CREATE_TICKET,
        expected_tools=("get_device_status", "get_recent_errors", "create_ticket"),
        expected_ok=True,
        expected_escalation=False,
    ),
    AgentBenchmarkCase(
        case_id="viewer-restart-denied",
        prompt="Restart SIM-014 service.",
        auth_token="viewer-token",  # noqa: S106  # nosec B106
        expected_intent=AgentIntent.REQUEST_SERVICE_RESTART,
        expected_tools=("get_recent_errors", "get_device_services", "restart_service"),
        expected_ok=False,
        expected_escalation=True,
    ),
)


def evaluate_agent(
    agent: AiEngineeringAgent,
    cases: tuple[AgentBenchmarkCase, ...] = DEFAULT_BENCHMARK_CASES,
) -> AgentBenchmarkResult:
    intent_correct = 0
    route_correct = 0
    outcome_correct = 0
    escalation_correct = 0
    hallucinated_tool_calls = 0
    failed_tool_calls = 0
    total_tool_calls = 0

    for case in cases:
        response = agent.handle(case.prompt, user_auth_token=case.auth_token)
        planned_tools = tuple(tool.tool_name for tool in response.selected_tools)
        actual_tools = tuple(step.tool_name for step in response.trace)
        intent_correct += int(response.intent == case.expected_intent)
        route_correct += int(planned_tools == case.expected_tools)
        outcome_correct += int(response.ok is case.expected_ok)
        escalation_correct += int(response.escalation_required is case.expected_escalation)
        hallucinated_tool_calls += len(
            [tool for tool in actual_tools if tool not in case.expected_tools]
        )
        failed_tool_calls += len([step for step in response.trace if not step.ok])
        total_tool_calls += len(response.trace)

    case_count = len(cases)
    return AgentBenchmarkResult(
        cases=case_count,
        intent_accuracy=_ratio(intent_correct, case_count),
        tool_route_accuracy=_ratio(route_correct, case_count),
        outcome_accuracy=_ratio(outcome_correct, case_count),
        escalation_accuracy=_ratio(escalation_correct, case_count),
        hallucinated_tool_calls=hallucinated_tool_calls,
        tool_failure_rate=_ratio(failed_tool_calls, total_tool_calls),
    )


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 3)
