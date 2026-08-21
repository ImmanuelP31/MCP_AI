from __future__ import annotations

from mcp_ops_ai_agent.tool_discovery.intent import RetrievalIntent, document_capabilities
from mcp_ops_ai_agent.tool_discovery.models import ToolDiscoveryResult


def complete_workflow_coverage(
    intent: RetrievalIntent,
    ranked_pool: list[ToolDiscoveryResult],
    *,
    top_k: int,
) -> list[ToolDiscoveryResult]:
    """Ensure the returned tool set covers the workflow, not just isolated relevance."""

    selected = list(ranked_pool[:top_k])
    selected_names = {result.tool.name for result in selected}
    required = required_workflow_capabilities(intent)
    if not required:
        return selected

    for capability in sorted(required - covered_capabilities(selected)):
        candidate = _best_candidate_for_capability(
            capability,
            ranked_pool,
            selected_names,
            intent,
        )
        if candidate is None:
            continue
        if len(selected) < top_k:
            selected.append(candidate)
            selected_names.add(candidate.tool.name)
            continue
        replacement_index = _replacement_index(selected, required)
        if replacement_index is None:
            continue
        selected_names.discard(selected[replacement_index].tool.name)
        selected[replacement_index] = candidate
        selected_names.add(candidate.tool.name)

    return sorted(
        selected,
        key=lambda item: (
            -_coverage_priority(item, required),
            -item.combined_score,
            -item.semantic_score,
            -item.lexical_score,
            item.tool.name,
        ),
    )[:top_k]


def required_workflow_capabilities(intent: RetrievalIntent) -> frozenset[str]:
    required = set(intent.requested_capabilities)
    if "investigate_failure" in intent.primary_intents:
        required.update({"build", "logs", "diagnostics"})
    if "diagnose_issue" in intent.primary_intents:
        required.add("diagnostics")
    if "create_record" in intent.primary_intents:
        required.add("ticket")
    if "lookup_knowledge" in intent.primary_intents:
        required.add("documentation")
    if "execute_operation" in intent.primary_intents:
        required.add("operation")
    return frozenset(required)


def covered_capabilities(results: list[ToolDiscoveryResult]) -> frozenset[str]:
    return frozenset(
        capability
        for result in results
        for capability in document_capabilities(result.tool)
    )


def _best_candidate_for_capability(
    capability: str,
    ranked_pool: list[ToolDiscoveryResult],
    selected_names: set[str],
    intent: RetrievalIntent,
) -> ToolDiscoveryResult | None:
    for candidate in ranked_pool:
        if candidate.tool.name in selected_names:
            continue
        if capability not in document_capabilities(candidate.tool):
            continue
        if _unsafe_backfill(candidate, intent):
            continue
        return candidate
    return None


def _replacement_index(
    selected: list[ToolDiscoveryResult],
    required: frozenset[str],
) -> int | None:
    selected_coverage = [
        document_capabilities(result.tool) & required
        for result in selected
    ]
    all_covered = set().union(*selected_coverage) if selected_coverage else set()
    if not all_covered:
        return _lowest_score_index(selected)
    replaceable: list[int] = []
    for index, capabilities in enumerate(selected_coverage):
        unique = capabilities - set().union(
            *[
                other
                for other_index, other in enumerate(selected_coverage)
                if other_index != index
            ]
        )
        if not unique:
            replaceable.append(index)
    if not replaceable:
        return None
    return min(replaceable, key=lambda index: selected[index].combined_score)


def _lowest_score_index(selected: list[ToolDiscoveryResult]) -> int | None:
    if not selected:
        return None
    return min(range(len(selected)), key=lambda index: selected[index].combined_score)


def _coverage_priority(result: ToolDiscoveryResult, required: frozenset[str]) -> int:
    return len(document_capabilities(result.tool) & required)


def _unsafe_backfill(result: ToolDiscoveryResult, intent: RetrievalIntent) -> bool:
    if "execute_operation" in intent.primary_intents:
        return False
    if result.tool.risk_level in {"HIGH", "CRITICAL"}:
        return True
    return False
