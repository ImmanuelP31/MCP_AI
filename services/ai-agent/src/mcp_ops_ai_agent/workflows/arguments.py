from __future__ import annotations

from typing import Any

from mcp_ops_ai_agent.workflows.models import WorkflowNode


class ArgumentBindingError(ValueError):
    pass


def resolve_node_arguments(
    node: WorkflowNode,
    dependency_outputs: dict[str, dict[str, Any]],
) -> WorkflowNode:
    if not node.argument_references:
        return node
    arguments = dict(node.arguments)
    for reference in node.argument_references:
        source_node_id = _reference_value(reference, "source_node_id")
        argument = _reference_value(reference, "argument")
        output_path = _reference_value(reference, "output_path")
        output = dependency_outputs.get(source_node_id)
        if output is None:
            raise ArgumentBindingError(f"Dependency output {source_node_id} is not available.")
        arguments[argument] = _read_path(output, output_path)
    return node.model_copy(update={"arguments": arguments}, deep=True)


def _reference_value(reference: Any, field_name: str) -> str:
    if isinstance(reference, dict):
        value = reference.get(field_name)
    else:
        value = getattr(reference, field_name)
    if not isinstance(value, str) or not value:
        raise ArgumentBindingError(f"Argument reference is missing {field_name}.")
    return value


def _read_path(payload: Any, path: str) -> Any:
    current = payload
    for segment in path.replace("[", ".").replace("]", "").split("."):
        if not segment:
            continue
        if isinstance(current, dict):
            if segment not in current:
                raise ArgumentBindingError(f"Output path {path} is missing.")
            current = current[segment]
            continue
        if isinstance(current, list) and segment.isdigit():
            index = int(segment)
            if index >= len(current):
                raise ArgumentBindingError(f"Output path {path} index is out of range.")
            current = current[index]
            continue
        raise ArgumentBindingError(f"Output path {path} cannot be resolved.")
    return current
