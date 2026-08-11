from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from mcp_ops_auth.rbac import ROLE_PERMISSIONS, Permission, Role
from mcp_ops_observability.metrics import (
    record_policy_approval_required,
    record_policy_bypass_attempt,
    record_policy_denial,
    record_policy_evaluation,
)
from mcp_ops_policy.tool_registry import TOOL_REGISTRY, RiskLevel, ToolMetadata

from mcp_ops_ai_agent.workflows.models import (
    PolicyDecision,
    WorkflowNode,
    WorkflowNodeStatus,
    WorkflowPolicyEvaluation,
)

READ_DECISIONS = {RiskLevel.READ_ONLY, RiskLevel.LOW}
HIGH_RISK = {RiskLevel.HIGH, RiskLevel.CRITICAL}


class WorkflowPolicyEvaluator:
    def __init__(self, *, registry: Mapping[str, ToolMetadata] | None = None) -> None:
        self.registry = TOOL_REGISTRY if registry is None else registry

    def evaluate(
        self,
        node: WorkflowNode,
        *,
        actor: str,
        role: str,
        environment: str,
        phase: str,
        proposed_node: WorkflowNode | None = None,
    ) -> WorkflowPolicyEvaluation:
        metadata = self.registry.get(node.tool_name)
        if metadata is None:
            evaluation = _record(
                actor=actor,
                role=role,
                tool=node.tool_name,
                resource=_resource(node),
                environment=environment,
                risk="UNKNOWN",
                decision=PolicyDecision.DENY,
                policy_rule="tool.exists",
                reason=f"Tool {node.tool_name} is not registered.",
            )
            _emit_metrics(evaluation)
            return evaluation

        if proposed_node is not None:
            _detect_llm_policy_bypass(proposed_node, metadata, role, environment)

        decision, rule, reason = self._decision(metadata, role, environment, phase, node)
        evaluation = _record(
            actor=actor,
            role=role,
            tool=metadata.tool_name,
            resource=_resource(node),
            environment=environment,
            risk=metadata.risk_level.value,
            decision=decision,
            policy_rule=rule,
            reason=reason,
        )
        _emit_metrics(evaluation)
        return evaluation

    def _decision(
        self,
        metadata: ToolMetadata,
        role: str,
        environment: str,
        phase: str,
        node: WorkflowNode,
    ) -> tuple[PolicyDecision, str, str]:
        normalized_env = _normalize_environment(environment)
        if phase == "execution" and not metadata.executable:
            return (
                PolicyDecision.DENY,
                "tool.executable",
                f"{metadata.tool_name} is catalog-only and cannot execute through MCP yet.",
            )
        if not metadata.enabled:
            return PolicyDecision.DENY, "tool.enabled", f"{metadata.tool_name} is disabled."
        if not _role_authorized(role, metadata):
            return (
                PolicyDecision.DENY,
                "rbac.required_permission",
                f"Role {role} is not authorized for {metadata.required_permission}.",
            )
        if _requires_context(metadata, normalized_env, node):
            return (
                PolicyDecision.REQUIRE_ADDITIONAL_CONTEXT,
                "context.required",
                "High-risk production actions require an explicit target resource.",
            )
        if metadata.risk_level in READ_DECISIONS:
            return PolicyDecision.ALLOW, "risk.read", "Read-only or low-risk tool is allowed."
        if metadata.requires_approval or metadata.risk_level in HIGH_RISK:
            return _environment_aware_operation_decision(metadata, role, normalized_env)
        return PolicyDecision.ALLOW, "risk.medium", "Medium-risk engineering action is allowed."


def transform_node_with_policy(
    node: WorkflowNode,
    evaluation: WorkflowPolicyEvaluation,
    metadata: ToolMetadata | None,
) -> WorkflowNode:
    approval_required = evaluation.decision == PolicyDecision.ALLOW_WITH_APPROVAL
    status = node.execution_status
    if evaluation.decision == PolicyDecision.DENY:
        status = WorkflowNodeStatus.DENIED
    elif evaluation.decision == PolicyDecision.REQUIRE_ADDITIONAL_CONTEXT:
        status = WorkflowNodeStatus.BLOCKED
    trusted_risk = metadata.risk_level.value if metadata is not None else evaluation.risk
    return node.model_copy(
        update={
            "risk_level": trusted_risk,
            "approval_required": approval_required,
            "policy_evaluation": evaluation,
            "execution_status": status,
        }
    )


def _environment_aware_operation_decision(
    metadata: ToolMetadata,
    role: str,
    environment: str,
) -> tuple[PolicyDecision, str, str]:
    if environment == "dev" and metadata.risk_level == RiskLevel.HIGH:
        return PolicyDecision.ALLOW, "environment.dev.high", "High-risk dev action is allowed."
    if environment == "dev" and metadata.risk_level == RiskLevel.CRITICAL:
        return (
            PolicyDecision.ALLOW_WITH_APPROVAL,
            "environment.dev.critical",
            "Critical dev action requires approval.",
        )
    if environment == "staging":
        if metadata.risk_level == RiskLevel.CRITICAL and role.upper() != "ADMIN":
            return (
                PolicyDecision.DENY,
                "environment.staging.critical",
                "Only admins may request critical staging actions.",
            )
        return (
            PolicyDecision.ALLOW_WITH_APPROVAL,
            "environment.staging.operation",
            "Staging operations require human approval.",
        )
    if environment == "production":
        if metadata.risk_level == RiskLevel.CRITICAL and role.upper() != "ADMIN":
            return (
                PolicyDecision.DENY,
                "environment.production.critical",
                "Critical production actions are denied for this role.",
            )
        return (
            PolicyDecision.ALLOW_WITH_APPROVAL,
            "environment.production.operation",
            "Production operations require human approval.",
        )
    return (
        PolicyDecision.ALLOW_WITH_APPROVAL,
        "environment.unknown.operation",
        "Unknown environments require approval for operational tools.",
    )


def _record(
    *,
    actor: str,
    role: str,
    tool: str,
    resource: str | None,
    environment: str,
    risk: str,
    decision: PolicyDecision,
    policy_rule: str,
    reason: str,
) -> WorkflowPolicyEvaluation:
    return WorkflowPolicyEvaluation(
        actor=actor,
        role=role,
        tool=tool,
        resource=resource,
        environment=_normalize_environment(environment),
        risk=risk,
        decision=decision,
        policy_rule=policy_rule,
        reason=reason,
        timestamp=datetime.now(UTC),
    )


def _role_authorized(role: str, metadata: ToolMetadata) -> bool:
    if metadata.required_roles:
        return role.upper() in {item.upper() for item in metadata.required_roles}
    try:
        permission = Permission(metadata.required_permission)
        role_value = Role(role.upper())
    except ValueError:
        return False
    return permission in ROLE_PERMISSIONS[role_value]


def _requires_context(metadata: ToolMetadata, environment: str, node: WorkflowNode) -> bool:
    return (
        environment == "production"
        and metadata.risk_level in HIGH_RISK
        and _resource(node) is None
    )


def _resource(node: WorkflowNode) -> str | None:
    for key in (
        "device_id",
        "service_name",
        "pipeline_id",
        "deployment_id",
        "repository",
        "ticket_id",
        "document_id",
    ):
        value = node.arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _detect_llm_policy_bypass(
    proposed_node: WorkflowNode,
    metadata: ToolMetadata,
    role: str,
    environment: str,
) -> None:
    trusted_requires_approval = (
        metadata.requires_approval or metadata.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}
    )
    risk_downgraded = proposed_node.risk_level != metadata.risk_level.value
    approval_downgraded = proposed_node.approval_required is False and trusted_requires_approval
    if risk_downgraded:
        record_policy_bypass_attempt(
            role=role,
            tool_name=metadata.tool_name,
            environment=_normalize_environment(environment),
            field="risk_level",
        )
    if approval_downgraded:
        record_policy_bypass_attempt(
            role=role,
            tool_name=metadata.tool_name,
            environment=_normalize_environment(environment),
            field="approval_required",
        )


def _emit_metrics(evaluation: WorkflowPolicyEvaluation) -> None:
    record_policy_evaluation(
        role=evaluation.role,
        tool_name=evaluation.tool,
        environment=evaluation.environment,
        decision=evaluation.decision.value,
    )
    if evaluation.decision == PolicyDecision.DENY:
        record_policy_denial(
            role=evaluation.role,
            tool_name=evaluation.tool,
            environment=evaluation.environment,
        )
    if evaluation.decision == PolicyDecision.ALLOW_WITH_APPROVAL:
        record_policy_approval_required(
            role=evaluation.role,
            tool_name=evaluation.tool,
            environment=evaluation.environment,
        )


def _normalize_environment(environment: str) -> str:
    normalized = environment.strip().lower()
    if normalized in {"development", "local"}:
        return "dev"
    if normalized in {"prod"}:
        return "production"
    return normalized or "dev"
