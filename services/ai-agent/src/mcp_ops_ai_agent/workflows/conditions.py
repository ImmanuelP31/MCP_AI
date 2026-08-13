from __future__ import annotations

import re
from typing import Any

from mcp_ops_ai_agent.workflows.arguments import ArgumentBindingError, read_output_path
from mcp_ops_ai_agent.workflows.models import ConditionOperator, WorkflowCondition, WorkflowNode


class ConditionEvaluationError(ValueError):
    pass


_LEGACY_CONDITION_PATTERN = re.compile(
    r"^(?P<source>[A-Za-z0-9_-]{1,120})\."
    r"(?P<path>[A-Za-z0-9_.\[\]-]{1,240})\s*"
    r"(?P<operator>==|!=|>=|<=|>|<)\s*"
    r"[\"']?(?P<value>[^\"']{1,240})[\"']?$"
)


def condition_is_satisfied(
    node: WorkflowNode,
    dependency_outputs: dict[str, dict[str, Any]],
) -> bool:
    condition = node.typed_condition or parse_legacy_condition(node.condition)
    if condition is None:
        return True
    if condition.source_node_id not in node.depends_on:
        raise ConditionEvaluationError(
            f"Condition source {condition.source_node_id} must be a dependency."
        )
    output = dependency_outputs.get(condition.source_node_id)
    if output is None:
        raise ConditionEvaluationError(
            f"Condition output {condition.source_node_id} is not available."
        )
    if condition.operator == ConditionOperator.EXISTS:
        try:
            read_output_path(output, condition.output_path)
        except ArgumentBindingError:
            return False
        return True
    try:
        actual = read_output_path(output, condition.output_path)
    except ArgumentBindingError as exc:
        raise ConditionEvaluationError(str(exc)) from exc
    return _compare(actual, condition.operator, condition.value)


def parse_legacy_condition(condition: str | None) -> WorkflowCondition | None:
    if condition is None:
        return None
    match = _LEGACY_CONDITION_PATTERN.match(condition.strip())
    if match is None:
        raise ConditionEvaluationError(f"Condition {condition!r} is not a supported expression.")
    return WorkflowCondition(
        source_node_id=match.group("source"),
        output_path=match.group("path"),
        operator=_operator_from_legacy(match.group("operator")),
        value=_coerce_scalar(match.group("value").strip()),
    )


def _operator_from_legacy(operator: str) -> ConditionOperator:
    return {
        "==": ConditionOperator.EQ,
        "!=": ConditionOperator.NE,
        ">": ConditionOperator.GT,
        ">=": ConditionOperator.GTE,
        "<": ConditionOperator.LT,
        "<=": ConditionOperator.LTE,
    }[operator]


def _compare(actual: Any, operator: ConditionOperator, expected: Any) -> bool:
    if operator == ConditionOperator.EQ:
        return bool(actual == expected)
    if operator == ConditionOperator.NE:
        return bool(actual != expected)
    if operator == ConditionOperator.CONTAINS:
        return bool(isinstance(actual, list | str | dict) and expected in actual)
    if operator in {
        ConditionOperator.GT,
        ConditionOperator.GTE,
        ConditionOperator.LT,
        ConditionOperator.LTE,
    }:
        if not isinstance(actual, int | float) or isinstance(actual, bool):
            return False
        if not isinstance(expected, int | float) or isinstance(expected, bool):
            return False
        if operator == ConditionOperator.GT:
            return bool(actual > expected)
        if operator == ConditionOperator.GTE:
            return bool(actual >= expected)
        if operator == ConditionOperator.LT:
            return bool(actual < expected)
        return bool(actual <= expected)
    return False


def _coerce_scalar(value: str) -> str | int | float | bool:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value
