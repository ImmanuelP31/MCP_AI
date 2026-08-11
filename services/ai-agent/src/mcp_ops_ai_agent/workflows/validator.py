from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from mcp_ops_auth.rbac import ROLE_PERMISSIONS, Permission, Role
from mcp_ops_observability.metrics import (
    record_argument_validation_failure,
    record_hallucinated_tool_call,
)
from mcp_ops_policy.tool_registry import TOOL_REGISTRY, RiskLevel, ToolMetadata

from mcp_ops_ai_agent.tool_discovery.service import default_input_schemas
from mcp_ops_ai_agent.workflows.models import (
    RetryStrategy,
    Workflow,
    WorkflowNode,
    WorkflowPlanDraft,
    WorkflowStatus,
    WorkflowValidationIssue,
)

MAX_WORKFLOW_NODES = 20
MAX_WORKFLOW_EDGES = 50


class WorkflowValidationError(ValueError):
    def __init__(self, issues: list[WorkflowValidationIssue]) -> None:
        super().__init__("Workflow validation failed.")
        self.issues = issues


class WorkflowValidator:
    def __init__(
        self,
        *,
        registry: Mapping[str, ToolMetadata] | None = None,
        input_schemas: Mapping[str, dict[str, Any]] | None = None,
        max_nodes: int = MAX_WORKFLOW_NODES,
        max_edges: int = MAX_WORKFLOW_EDGES,
    ) -> None:
        self.registry = TOOL_REGISTRY if registry is None else registry
        self.input_schemas = dict(input_schemas or default_input_schemas())
        self.max_nodes = max_nodes
        self.max_edges = max_edges

    def validate(
        self,
        draft: WorkflowPlanDraft,
        *,
        created_by: str,
        role: str,
        allowed_tool_names: set[str],
        target_environment: str = "dev",
    ) -> Workflow:
        issues: list[WorkflowValidationIssue] = []
        if len(draft.nodes) > self.max_nodes:
            issues.append(_issue("workflow_too_large", "Workflow exceeds maximum node count."))
        if len(draft.edges) > self.max_edges:
            issues.append(_issue("workflow_too_large", "Workflow exceeds maximum edge count."))

        node_ids = [node.id for node in draft.nodes]
        if len(node_ids) != len(set(node_ids)):
            issues.append(_issue("duplicate_node_id", "Workflow node IDs must be unique."))
        node_id_set = set(node_ids)

        normalized_nodes: list[WorkflowNode] = []
        for node in draft.nodes:
            metadata = self.registry.get(node.tool_name)
            if metadata is None:
                record_hallucinated_tool_call(
                    planner_model=draft.planner_model,
                    tool_name=node.tool_name,
                )
                issues.append(
                    _issue("unknown_tool", f"Tool {node.tool_name} does not exist.", node.id)
                )
                normalized_nodes.append(node)
                continue
            if node.tool_name not in allowed_tool_names:
                record_hallucinated_tool_call(
                    planner_model=draft.planner_model,
                    tool_name=node.tool_name,
                )
                issues.append(
                    _issue(
                        "tool_not_discovered",
                        f"Tool {node.tool_name} was not in the policy-filtered discovery set.",
                        node.id,
                    )
                )
            if not metadata.enabled:
                issues.append(
                    _issue("tool_disabled", f"Tool {node.tool_name} is disabled.", node.id)
                )
            issues.extend(self._validate_arguments(node, role, metadata))
            normalized_nodes.append(_classify_risk(node, metadata))

        issues.extend(_validate_dependencies(draft.nodes, node_id_set))
        issues.extend(_validate_edges(draft, node_id_set))
        issues.extend(_validate_acyclic(draft))
        if issues:
            raise WorkflowValidationError(issues)
        workflow = Workflow(
            user_request=draft.user_request,
            status=WorkflowStatus.VALIDATED,
            created_by=created_by,
            target_environment=target_environment,
            planner_model=draft.planner_model,
            confidence=draft.confidence,
            nodes=normalized_nodes,
            edges=draft.edges,
        )
        return workflow.model_copy(
            update={
                "nodes": [
                    node.model_copy(update={"workflow_id": workflow.id})
                    for node in normalized_nodes
                ]
            }
        )

    def _validate_arguments(
        self,
        node: WorkflowNode,
        role: str,
        metadata: ToolMetadata,
    ) -> list[WorkflowValidationIssue]:
        schema = self.input_schemas.get(node.tool_name)
        if schema is None:
            return []
        payload = {"actor_role": role, **node.arguments}
        issues: list[WorkflowValidationIssue] = []
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            return [_issue("invalid_schema", "Tool input schema is malformed.", node.id)]
        allowed = set(properties)
        rejected = sorted(set(payload) - allowed)
        if schema.get("additionalProperties") is False and rejected:
            record_argument_validation_failure(
                tool_name=node.tool_name,
                reason="unsupported_fields",
            )
            issues.append(
                _issue(
                    "invalid_arguments",
                    "Unsupported argument fields: " + ", ".join(rejected) + ".",
                    node.id,
                )
            )
        required = schema.get("required", [])
        if isinstance(required, list):
            missing = sorted(
                str(field)
                for field in required
                if str(field) not in payload
                and not (str(field) == "approval_token" and metadata.requires_approval)
            )
            if missing:
                record_argument_validation_failure(
                    tool_name=node.tool_name,
                    reason="missing_required_fields",
                )
                issues.append(
                    _issue(
                        "invalid_arguments",
                        "Missing required arguments: " + ", ".join(missing) + ".",
                        node.id,
                    )
                )
        for field_name, value in payload.items():
            field_schema = properties.get(field_name)
            if isinstance(field_schema, dict):
                issues.extend(_validate_field(node.id, field_name, value, field_schema))
        return issues


def _classify_risk(node: WorkflowNode, metadata: ToolMetadata) -> WorkflowNode:
    approval_required = (
        metadata.requires_approval
        or metadata.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}
        or node.approval_required
    )
    return node.model_copy(
        update={
            "tool_server": metadata.server,
            "risk_level": metadata.risk_level.value,
            "approval_required": approval_required,
            "max_retries": metadata.default_max_retries,
            "retry_strategy": RetryStrategy(metadata.retry_strategy),
            "timeout_seconds": metadata.timeout_seconds,
            "compensation_tool": metadata.compensation_tool,
        }
    )


def _validate_field(
    node_id: str,
    field_name: str,
    value: Any,
    field_schema: dict[str, Any],
) -> list[WorkflowValidationIssue]:
    issues: list[WorkflowValidationIssue] = []
    expected_type = field_schema.get("type")
    if expected_type == "string" and not isinstance(value, str):
        issues.append(_issue("invalid_arguments", f"{field_name} must be a string.", node_id))
    if expected_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
        issues.append(_issue("invalid_arguments", f"{field_name} must be an integer.", node_id))
    if expected_type == "boolean" and not isinstance(value, bool):
        issues.append(_issue("invalid_arguments", f"{field_name} must be a boolean.", node_id))
    if expected_type == "object" and not isinstance(value, dict):
        issues.append(_issue("invalid_arguments", f"{field_name} must be an object.", node_id))
    if expected_type == "array" and not isinstance(value, list):
        issues.append(_issue("invalid_arguments", f"{field_name} must be an array.", node_id))
    pattern = field_schema.get("pattern")
    if isinstance(pattern, str) and isinstance(value, str) and not re.match(pattern, value):
        issues.append(_issue("invalid_arguments", f"{field_name} does not match pattern.", node_id))
    min_length = field_schema.get("minLength")
    if isinstance(min_length, int) and isinstance(value, str) and len(value) < min_length:
        issues.append(_issue("invalid_arguments", f"{field_name} is too short.", node_id))
    max_length = field_schema.get("maxLength")
    if isinstance(max_length, int) and isinstance(value, str) and len(value) > max_length:
        issues.append(_issue("invalid_arguments", f"{field_name} is too long.", node_id))
    enum_values = field_schema.get("enum")
    if isinstance(enum_values, list) and value not in enum_values:
        issues.append(
            _issue("invalid_arguments", f"{field_name} is not an allowed value.", node_id)
        )
    return issues


def _validate_dependencies(
    nodes: list[WorkflowNode],
    node_ids: set[str],
) -> list[WorkflowValidationIssue]:
    issues: list[WorkflowValidationIssue] = []
    for node in nodes:
        for dependency in node.depends_on:
            if dependency not in node_ids:
                issues.append(
                    _issue(
                        "missing_dependency",
                        f"Dependency {dependency} does not exist.",
                        node.id,
                    )
                )
    return issues


def _validate_edges(
    draft: WorkflowPlanDraft,
    node_ids: set[str],
) -> list[WorkflowValidationIssue]:
    issues: list[WorkflowValidationIssue] = []
    for edge in draft.edges:
        if edge.source not in node_ids:
            issues.append(_issue("missing_edge_source", f"Edge source {edge.source} missing."))
        if edge.destination not in node_ids:
            issues.append(
                _issue("missing_edge_destination", f"Edge destination {edge.destination} missing.")
            )
    return issues


def _validate_acyclic(draft: WorkflowPlanDraft) -> list[WorkflowValidationIssue]:
    graph: dict[str, list[str]] = {node.id: list(node.depends_on) for node in draft.nodes}
    for edge in draft.edges:
        graph.setdefault(edge.destination, []).append(edge.source)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return False
        if node_id in visited:
            return True
        visiting.add(node_id)
        for dependency in graph.get(node_id, []):
            if dependency in graph and not visit(dependency):
                return False
        visiting.remove(node_id)
        visited.add(node_id)
        return True

    for node_id in graph:
        if not visit(node_id):
            return [_issue("cycle_detected", "Workflow graph must be acyclic.", node_id)]
    return []


def _role_authorized(role: str, metadata: ToolMetadata) -> bool:
    if metadata.required_roles:
        return role.upper() in {item.upper() for item in metadata.required_roles}
    try:
        permission = Permission(metadata.required_permission)
    except ValueError:
        return False
    try:
        role_value = Role(role.upper())
    except ValueError:
        return False
    permissions = ROLE_PERMISSIONS[role_value]
    return permission in permissions


def _issue(code: str, message: str, node_id: str | None = None) -> WorkflowValidationIssue:
    return WorkflowValidationIssue(code=code, message=message, node_id=node_id)
