from mcp_ops_ai_agent.capabilities import (
    CapabilityGraphService,
    compare_capability_constrained_planning,
)
from mcp_ops_ai_agent.capabilities.models import CapabilityPathRequest
from mcp_ops_policy.tool_registry import RiskLevel, ToolMetadata


def test_capability_graph_finds_failed_build_ticket_path() -> None:
    service = CapabilityGraphService()

    path = service.find_path(
        CapabilityPathRequest(
            source="repository:payments-api",
            goal="create_issue_for_latest_failed_build",
            role="OPERATOR",
            environment="staging",
        )
    )

    assert path.reachable is True
    assert path.policy_compliant is True
    assert path.tools == [
        "get_build_status",
        "get_failed_jobs",
        "get_pipeline_logs",
        "analyze_build_failure",
        "create_ticket",
    ]


def test_capability_graph_reports_unreachable_goal() -> None:
    service = CapabilityGraphService()

    path = service.find_path(
        CapabilityPathRequest(
            source="repository:payments-api",
            goal="ship_moonbase",
            role="OPERATOR",
            environment="staging",
        )
    )

    assert path.reachable is False
    assert path.policy_compliant is False
    assert "No policy-compliant path" in path.explanation


def test_capability_graph_blocks_policy_denied_path() -> None:
    service = CapabilityGraphService()

    path = service.find_path(
        CapabilityPathRequest(
            source="deployment:current",
            goal="deleted_deployment",
            role="OPERATOR",
            environment="production",
        )
    )

    assert path.reachable is False
    assert path.policy_compliant is False


def test_capability_graph_can_return_unfiltered_shortest_path() -> None:
    service = CapabilityGraphService()

    path = service.find_path(
        CapabilityPathRequest(
            source="deployment:current",
            goal="deleted_deployment",
            role="OPERATOR",
            environment="production",
            strategy="shortest",
        )
    )

    assert path.reachable is True
    assert path.tools == ["delete_bad_deployment"]


def test_capability_graph_prefers_lower_risk_alternative_from_tool_declarations() -> None:
    registry = {
        "fast_high": _metadata(
            "fast_high",
            RiskLevel.HIGH,
            input_resource_types=["repository"],
            output_resource_types=["ticket"],
            cost_weight=1.0,
        ),
        "safe_low": _metadata(
            "safe_low",
            RiskLevel.READ_ONLY,
            input_resource_types=["repository"],
            output_resource_types=["ticket"],
            cost_weight=2.0,
        ),
    }
    service = CapabilityGraphService(registry=registry)

    path = service.find_path(
        CapabilityPathRequest(
            source="repository:payments-api",
            goal="ticket",
            role="ENGINEER",
            environment="dev",
            strategy="lowest_risk",
        )
    )

    assert path.reachable is True
    assert path.tools == ["safe_low"]


def test_capability_graph_handles_cycles_without_infinite_loop() -> None:
    registry = {
        "alpha_to_beta": _metadata(
            "alpha_to_beta",
            RiskLevel.READ_ONLY,
            input_resource_types=["alpha"],
            output_resource_types=["beta"],
        ),
        "beta_to_alpha": _metadata(
            "beta_to_alpha",
            RiskLevel.READ_ONLY,
            input_resource_types=["beta"],
            output_resource_types=["alpha"],
        ),
        "beta_to_gamma": _metadata(
            "beta_to_gamma",
            RiskLevel.READ_ONLY,
            input_resource_types=["beta"],
            output_resource_types=["gamma"],
        ),
    }
    service = CapabilityGraphService(registry=registry)

    path = service.find_path(
        CapabilityPathRequest(
            source="alpha:source",
            goal="gamma",
            role="ENGINEER",
            environment="dev",
        )
    )

    assert path.reachable is True
    assert path.tools == ["alpha_to_beta", "beta_to_gamma"]


def test_capability_graph_handles_missing_tool_and_disabled_server() -> None:
    service = CapabilityGraphService()

    assert service.find_resources_affected_by_tool("missing_tool") == []

    path = service.find_path(
        CapabilityPathRequest(
            source="repository:payments-api",
            goal="investigate_failed_build",
            role="OPERATOR",
            environment="staging",
            disabled_servers=["cicd-mcp"],
        )
    )

    assert path.reachable is False


def test_capability_graph_evaluation_improves_hallucination_and_policy_rates() -> None:
    result = compare_capability_constrained_planning(CapabilityGraphService())

    assert result.graph_valid_tool_sequence_rate >= result.llm_only_valid_tool_sequence_rate
    assert result.graph_hallucinated_tool_rate == 0.0
    assert result.graph_policy_violation_rate == 0.0


def _metadata(
    name: str,
    risk: RiskLevel,
    *,
    input_resource_types: list[str],
    output_resource_types: list[str],
    cost_weight: float = 1.0,
) -> ToolMetadata:
    return ToolMetadata(
        tool_name=name,
        domain="test",
        description=f"{name} test capability",
        risk_level=risk,
        required_permission="test:read",
        requires_approval=risk in {RiskLevel.HIGH, RiskLevel.CRITICAL},
        server="test-mcp",
        category="test",
        tags=["test"],
        required_roles=["ENGINEER", "OPERATOR", "ADMIN"],
        input_resource_types=input_resource_types,
        output_resource_types=output_resource_types,
        cost_weight=cost_weight,
        executable=False,
        rate_limit="60/minute",
    )
