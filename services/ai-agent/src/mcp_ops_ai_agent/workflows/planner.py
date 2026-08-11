from __future__ import annotations

import json
from typing import Protocol

from pydantic import ValidationError

from mcp_ops_ai_agent.engineering_rag.models import KnowledgeSearchResult
from mcp_ops_ai_agent.tool_discovery.models import ToolDocument
from mcp_ops_ai_agent.workflows.models import WorkflowEdge, WorkflowNode, WorkflowPlanDraft


class WorkflowPlanner(Protocol):
    planner_model: str

    def plan(
        self,
        user_request: str,
        tools: list[ToolDocument],
        *,
        role: str,
        knowledge: list[KnowledgeSearchResult] | None = None,
    ) -> WorkflowPlanDraft:
        """Create a typed workflow draft from a safe tool subset."""


class PlannerOutputError(ValueError):
    pass


class DeterministicWorkflowPlanner:
    planner_model = "deterministic-workflow-planner-v1"

    def plan(
        self,
        user_request: str,
        tools: list[ToolDocument],
        *,
        role: str,
        knowledge: list[KnowledgeSearchResult] | None = None,
    ) -> WorkflowPlanDraft:
        del role
        available = {tool.name: tool for tool in tools}
        normalized = user_request.lower()
        if "build" in normalized or "pipeline" in normalized or "ci" in normalized:
            return _build_failure_workflow(user_request, available, knowledge or [])
        if "deploy" in normalized or "deployment" in normalized or "release" in normalized:
            return _deployment_workflow(user_request, available, knowledge or [])
        if "restart" in normalized and "service" in normalized:
            return _service_restart_workflow(user_request, available, knowledge or [])
        if "ticket" in normalized:
            return _ticket_workflow(user_request, available, knowledge or [])
        if "documentation" in normalized or "docs" in normalized or "runbook" in normalized:
            return _documentation_workflow(user_request, available, knowledge or [])
        return _general_investigation_workflow(user_request, available, knowledge or [])


class JsonWorkflowPlanner:
    """Test/support planner for validating malformed or external JSON planner output."""

    planner_model = "json-workflow-planner-test"

    def __init__(self, raw_json: str) -> None:
        self.raw_json = raw_json

    def plan(
        self,
        user_request: str,
        tools: list[ToolDocument],
        *,
        role: str,
        knowledge: list[KnowledgeSearchResult] | None = None,
    ) -> WorkflowPlanDraft:
        del user_request, tools, role, knowledge
        try:
            json.loads(self.raw_json)
            return WorkflowPlanDraft.model_validate_json(self.raw_json)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise PlannerOutputError("Planner returned malformed workflow JSON.") from exc


def _build_failure_workflow(
    user_request: str,
    available: dict[str, ToolDocument],
    knowledge: list[KnowledgeSearchResult],
) -> WorkflowPlanDraft:
    nodes: list[WorkflowNode] = []
    edges: list[WorkflowEdge] = []
    existing_ids: set[str] = set()
    for node_id, tool_name, depends_on in [
        ("build_status", "get_build_status", []),
        ("pipeline_logs", "get_pipeline_logs", ["build_status"]),
        (
            "recent_commits",
            _first_available(available, "get_recent_commits", "get_commit_history"),
            ["pipeline_logs"],
        ),
        ("failure_analysis", "analyze_build_failure", ["pipeline_logs", "recent_commits"]),
    ]:
        if tool_name in available:
            safe_depends_on = [dep for dep in depends_on if dep in existing_ids]
            nodes.append(
                _node(
                    node_id,
                    available[tool_name],
                    user_request,
                    depends_on=safe_depends_on,
                    knowledge_references=_references_from_knowledge(knowledge, node_id),
                )
            )
            edges.extend(WorkflowEdge(source=dep, destination=node_id) for dep in safe_depends_on)
            existing_ids.add(node_id)
    request_text = user_request.lower()
    requested_record_tool = None
    if "issue" in request_text and "create_issue" in available:
        requested_record_tool = "create_issue"
    elif ("ticket" in request_text or "if" in request_text) and "create_ticket" in available:
        requested_record_tool = "create_ticket"
    if requested_record_tool:
        safe_depends_on = ["failure_analysis"] if "failure_analysis" in existing_ids else []
        nodes.append(
            _node(
                requested_record_tool,
                available[requested_record_tool],
                user_request,
                depends_on=safe_depends_on,
                condition="failure_analysis.source == 'source_code_failure'",
                knowledge_references=_references_from_knowledge(knowledge, requested_record_tool),
            )
        )
        if safe_depends_on:
            edges.append(
                WorkflowEdge(
                    source="failure_analysis",
                    destination=requested_record_tool,
                    condition="source_code_failure",
                )
            )
    return WorkflowPlanDraft(
        user_request=user_request,
        planner_model=DeterministicWorkflowPlanner.planner_model,
        confidence=0.88,
        nodes=nodes or _fallback_nodes(user_request, available, knowledge),
        edges=edges,
    )


def _deployment_workflow(
    user_request: str,
    available: dict[str, ToolDocument],
    knowledge: list[KnowledgeSearchResult],
) -> WorkflowPlanDraft:
    ordered = [
        ("build_status", "get_build_status", []),
        ("run_tests", "run_tests", ["build_status"]),
        ("deploy_staging", "deploy_staging", ["run_tests"]),
        ("deployment_status", "get_deployment_status", ["deploy_staging"]),
    ]
    return _linear_workflow(
        user_request,
        available,
        ordered,
        confidence=0.87,
        knowledge=knowledge,
    )


def _service_restart_workflow(
    user_request: str,
    available: dict[str, ToolDocument],
    knowledge: list[KnowledgeSearchResult],
) -> WorkflowPlanDraft:
    ordered = [
        ("recent_errors", "get_recent_errors", []),
        ("device_services", "get_device_services", ["recent_errors"]),
        ("restart_service", "restart_service", ["device_services"]),
    ]
    return _linear_workflow(user_request, available, ordered, confidence=0.84, knowledge=knowledge)


def _ticket_workflow(
    user_request: str,
    available: dict[str, ToolDocument],
    knowledge: list[KnowledgeSearchResult],
) -> WorkflowPlanDraft:
    ordered = [
        ("device_status", "get_device_status", []),
        ("recent_errors", "get_recent_errors", ["device_status"]),
        ("create_ticket", "create_ticket", ["recent_errors"]),
    ]
    return _linear_workflow(user_request, available, ordered, confidence=0.86, knowledge=knowledge)


def _documentation_workflow(
    user_request: str,
    available: dict[str, ToolDocument],
    knowledge: list[KnowledgeSearchResult],
) -> WorkflowPlanDraft:
    ordered = [
        (
            "search_documentation",
            _first_available(available, "search_documentation", "search_knowledge"),
            [],
        ),
        (
            "get_runbook",
            _first_available(available, "get_runbook", "get_procedure"),
            ["search_documentation"],
        ),
    ]
    return _linear_workflow(user_request, available, ordered, confidence=0.82, knowledge=knowledge)


def _general_investigation_workflow(
    user_request: str,
    available: dict[str, ToolDocument],
    knowledge: list[KnowledgeSearchResult],
) -> WorkflowPlanDraft:
    return WorkflowPlanDraft(
        user_request=user_request,
        planner_model=DeterministicWorkflowPlanner.planner_model,
        confidence=0.72,
        nodes=_fallback_nodes(user_request, available, knowledge),
        edges=[],
    )


def _linear_workflow(
    user_request: str,
    available: dict[str, ToolDocument],
    ordered: list[tuple[str, str, list[str]]],
    *,
    confidence: float,
    knowledge: list[KnowledgeSearchResult],
) -> WorkflowPlanDraft:
    nodes: list[WorkflowNode] = []
    edges: list[WorkflowEdge] = []
    existing_ids: set[str] = set()
    for node_id, tool_name, depends_on in ordered:
        if tool_name not in available:
            continue
        safe_depends_on = [dep for dep in depends_on if dep in existing_ids]
        nodes.append(
            _node(
                node_id,
                available[tool_name],
                user_request,
                depends_on=safe_depends_on,
                knowledge_references=_references_from_knowledge(knowledge, node_id),
            )
        )
        edges.extend(WorkflowEdge(source=dep, destination=node_id) for dep in safe_depends_on)
        existing_ids.add(node_id)
    return WorkflowPlanDraft(
        user_request=user_request,
        planner_model=DeterministicWorkflowPlanner.planner_model,
        confidence=confidence,
        nodes=nodes or _fallback_nodes(user_request, available, knowledge),
        edges=edges,
    )


def _fallback_nodes(
    user_request: str,
    available: dict[str, ToolDocument],
    knowledge: list[KnowledgeSearchResult] | None = None,
) -> list[WorkflowNode]:
    return [
        _node(
            f"tool_{index}",
            tool,
            user_request,
            knowledge_references=_references_from_knowledge(knowledge or [], f"tool_{index}"),
        )
        for index, tool in enumerate(list(available.values())[:3], start=1)
    ]


def _node(
    node_id: str,
    tool: ToolDocument,
    user_request: str,
    *,
    depends_on: list[str] | None = None,
    condition: str | None = None,
    knowledge_references: list[str] | None = None,
) -> WorkflowNode:
    return WorkflowNode(
        id=node_id,
        tool_name=tool.name,
        tool_server=tool.server,
        description=tool.description,
        arguments=_arguments_for(tool, user_request),
        depends_on=depends_on or [],
        condition=condition,
        risk_level=tool.risk_level,
        approval_required=tool.risk_level in {"HIGH", "CRITICAL"},
        knowledge_references=knowledge_references or [],
    )


def _arguments_for(tool: ToolDocument, user_request: str) -> dict[str, object]:
    github_repository = "ImmanuelP31/MCP_AI"
    if tool.name in {
        "get_build_status",
        "get_latest_failed_build",
        "get_workflow_runs",
        "get_recent_commits",
        "get_commit_history",
        "list_recent_commits",
    }:
        return {"repository": github_repository}
    if tool.name in {"get_failed_jobs", "get_workflow_run_jobs"}:
        return {"repository": github_repository, "run_id": 9001}
    if tool.name in {"get_pipeline_logs", "get_job_logs"}:
        return {"repository": github_repository, "job_id": 101}
    if tool.name == "get_commit_details":
        return {"repository": github_repository, "sha": "abc1234"}
    if tool.name == "get_changed_files":
        return {"repository": github_repository, "head": "abc1234"}
    if tool.name == "create_issue":
        return {
            "repository": github_repository,
            "title": "Investigate failed GitHub Actions build",
            "body": f"Workflow-created GitHub issue from request: {user_request[:500]}",
            "labels": ["mcp", "automated-investigation"],
        }
    if tool.name == "rerun_workflow":
        return {
            "repository": github_repository,
            "run_id": 9001,
            "reason": "Approved CI rerun after governed investigation.",
        }
    device_tools = {
        "get_device_status",
        "get_device_services",
        "get_recent_errors",
        "restart_service",
    }
    if tool.name in device_tools:
        arguments: dict[str, object] = {"device_id": "SIM-014"}
        if tool.name == "restart_service":
            arguments["service_name"] = "sensor-ingestor"
            arguments["reason"] = "Workflow requested governed service recovery."
        return arguments
    if tool.name == "create_ticket":
        return {
            "device_id": "SIM-014",
            "title": "Investigate engineering workflow finding",
            "description": f"Workflow-created ticket from request: {user_request[:500]}",
            "priority": "HIGH",
            "team": "Engineering Operations",
            "diagnostic_evidence": {"source": "workflow_planner"},
        }
    return {"query": user_request[:500]}


def _first_available(available: dict[str, ToolDocument], *names: str) -> str:
    for name in names:
        if name in available:
            return name
    return names[0]


def _references_from_knowledge(
    knowledge: list[KnowledgeSearchResult],
    node_id: str,
) -> list[str]:
    if not knowledge:
        return []
    node_terms = set(node_id.replace("_", " ").split())
    selected: list[str] = []
    for result in knowledge:
        text = " ".join(
            [
                result.chunk.metadata.document_type,
                result.chunk.metadata.title,
                result.chunk.text,
            ]
        ).lower()
        if node_terms & set(text.replace("-", " ").split()):
            selected.append(result.citation_id)
    if not selected:
        selected = [result.citation_id for result in knowledge[:2]]
    return list(dict.fromkeys(selected[:4]))
