from mcp_ops_policy.tool_registry import TOOL_REGISTRY, RiskLevel


def test_high_risk_tools_require_approval() -> None:
    for tool in TOOL_REGISTRY.values():
        if tool.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            assert tool.requires_approval


def test_registered_tools_have_required_metadata() -> None:
    for name, tool in TOOL_REGISTRY.items():
        assert name == tool.tool_name
        assert tool.domain
        assert tool.description
        assert tool.required_permission
        assert tool.rate_limit
