from __future__ import annotations

import json
from typing import Any

import pytest
from mcp_ops_ai_agent.engineering_rag.models import (
    EngineeringDocumentMetadata,
    EngineeringKnowledgeSearchResponse,
    KnowledgeChunk,
    KnowledgeSearchResult,
)
from mcp_ops_ai_agent.workflows.arguments import resolve_node_arguments
from mcp_ops_ai_agent.workflows.models import (
    PlannerDecisionType,
    WorkflowNode,
    WorkflowPlanDraft,
    WorkflowPlanRequest,
)
from mcp_ops_ai_agent.workflows.planner import (
    JsonWorkflowPlanner,
    LLMWorkflowPlanner,
    PlannerConfigurationError,
    PlannerOutputError,
    workflow_planner_from_settings,
)
from mcp_ops_ai_agent.workflows.policy import WorkflowPolicyEvaluator
from mcp_ops_ai_agent.workflows.service import (
    WorkflowPlanningService,
    _augment_tools_from_knowledge,
)
from mcp_ops_ai_agent.workflows.validator import WorkflowValidationError, WorkflowValidator
from mcp_ops_common.config import Settings
from mcp_ops_observability.metrics import metrics_response


def test_valid_linear_workflow_is_planned_from_authorized_tools() -> None:
    service = WorkflowPlanningService()

    result = service.plan(
        WorkflowPlanRequest(
            user_request="Create a maintenance ticket for SIM-014.",
            role="ENGINEER",
            created_by="engineer",
            top_k=20,
        )
    )

    assert result.ok is True
    assert result.workflow.status == "VALIDATED"
    assert result.planner_provider == "deterministic"
    assert result.retrieval_backend
    assert [node.tool_name for node in result.workflow.nodes][-1] == "create_ticket"
    assert result.workflow.edges


def test_dag_workflow_contains_conditional_ticket_step() -> None:
    service = WorkflowPlanningService()

    result = service.plan(
        WorkflowPlanRequest(
            user_request=(
                "Check why the latest build failed and create a ticket if the problem "
                "comes from our code."
            ),
            role="ENGINEER",
            created_by="engineer",
            top_k=10,
        )
    )

    nodes = {node.id: node for node in result.workflow.nodes}
    assert "failure_analysis" in nodes
    assert nodes["create_ticket"].condition == "failure_analysis.source == 'source_code_failure'"
    assert nodes["create_ticket"].typed_condition is not None
    assert nodes["create_ticket"].typed_condition.output_path == "data.source"
    assert any(edge.condition == "source_code_failure" for edge in result.workflow.edges)


def test_build_failure_workflow_can_create_github_issue() -> None:
    service = WorkflowPlanningService()

    result = service.plan(
        WorkflowPlanRequest(
            user_request=(
                "Check why the latest GitHub build failed and create a GitHub issue if "
                "the problem comes from our code."
            ),
            role="ENGINEER",
            created_by="engineer",
            top_k=15,
        )
    )

    nodes = {node.id: node for node in result.workflow.nodes}
    assert "create_issue" in nodes
    assert nodes["create_issue"].arguments["repository"] == "ImmanuelP31/MCP_AI"
    assert nodes["create_issue"].condition == "failure_analysis.source == 'source_code_failure'"


def test_cycle_rejection_reports_graph_error() -> None:
    draft = WorkflowPlanDraft(
        user_request="Search device status.",
        planner_model="test",
        confidence=0.8,
        nodes=[
            _node("a", "get_device_status", depends_on=["b"]),
            _node("b", "get_device_health", depends_on=["a"]),
        ],
        edges=[],
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowValidator().validate(
            draft,
            created_by="engineer",
            role="ENGINEER",
            allowed_tool_names={"get_device_status", "get_device_health"},
        )

    assert _codes(exc_info.value) == {"cycle_detected"}


def test_nonexistent_tool_is_rejected() -> None:
    draft = WorkflowPlanDraft(
        user_request="Use a fake tool.",
        planner_model="test",
        confidence=0.8,
        nodes=[_node("fake", "totally_fake_tool")],
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowValidator().validate(
            draft,
            created_by="engineer",
            role="ENGINEER",
            allowed_tool_names={"totally_fake_tool"},
        )

    assert "unknown_tool" in _codes(exc_info.value)


def test_unauthorized_tool_is_denied_by_policy_before_execution() -> None:
    evaluation = WorkflowPolicyEvaluator().evaluate(
        _node("restart", "restart_service"),
        actor="viewer",
        role="VIEWER",
        environment="production",
        phase="planning",
    )

    assert evaluation.decision == "DENY"
    assert evaluation.policy_rule == "rbac.required_permission"


def test_invalid_arguments_are_rejected() -> None:
    draft = WorkflowPlanDraft(
        user_request="Create a ticket.",
        planner_model="test",
        confidence=0.8,
        nodes=[_node("ticket", "create_ticket", arguments={"title": "Missing fields"})],
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowValidator().validate(
            draft,
            created_by="engineer",
            role="ENGINEER",
            allowed_tool_names={"create_ticket"},
        )

    assert "invalid_arguments" in _codes(exc_info.value)


def test_high_risk_workflow_is_flagged_for_approval_without_model_token() -> None:
    service = WorkflowPlanningService()

    result = service.plan(
        WorkflowPlanRequest(
            user_request="Restart SIM-014 service.",
            role="OPERATOR",
            created_by="operator",
            target_environment="production",
            top_k=8,
        )
    )

    restart = next(node for node in result.workflow.nodes if node.tool_name == "restart_service")
    assert restart.approval_required is True
    assert "approval_token" not in restart.arguments


def test_planner_malformed_json_is_rejected() -> None:
    service = WorkflowPlanningService(planner=JsonWorkflowPlanner("{"))

    with pytest.raises(PlannerOutputError) as exc_info:
        service.plan(
            WorkflowPlanRequest(
                user_request="Plan a build workflow.",
                role="ENGINEER",
                created_by="engineer",
            )
        )

    assert exc_info.value.stage == "json_parse"
    assert exc_info.value.reason


def test_llm_workflow_planner_records_retry_failure_reason() -> None:
    service = WorkflowPlanningService()
    tools = service.discovery.safe_tools_for_planner(
        "Check why the latest build failed.",
        role="ENGINEER",
        top_k=10,
    )
    client = FakeWorkflowPlanClient(["{", "{"])

    with pytest.raises(PlannerOutputError) as exc_info:
        LLMWorkflowPlanner(client, model_name="test-model").plan(
            "Check why the latest build failed.",
            tools,
            role="ENGINEER",
        )

    assert exc_info.value.retry_attempted is True
    assert exc_info.value.retry_failure_reason


class FakeWorkflowPlanClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def complete_json(self, *, system_prompt: str, user_payload: dict[str, Any]) -> str:
        self.calls.append({"system_prompt": system_prompt, "user_payload": user_payload})
        return self.responses.pop(0)


def test_llm_workflow_planner_returns_typed_schema_from_authorized_tool_subset() -> None:
    service = WorkflowPlanningService()
    tools = service.discovery.safe_tools_for_planner(
        "Check why the latest build failed.",
        role="ENGINEER",
        top_k=10,
    )
    payload = {
        "user_request": "Check why the latest build failed.",
        "planner_model": "ignored-by-test",
        "confidence": 0.8,
        "nodes": [
            {
                "id": "build_status",
                "tool_name": "get_build_status",
                "tool_server": "cicd-mcp",
                "description": "Read build status.",
                "arguments": {"repository": "ImmanuelP31/MCP_AI"},
                "risk_level": "READ_ONLY",
            }
        ],
        "edges": [],
    }
    client = FakeWorkflowPlanClient([json.dumps(payload)])

    draft = LLMWorkflowPlanner(client, model_name="test-model").plan(
        "Check why the latest build failed.",
        tools,
        role="ENGINEER",
    )

    assert draft.nodes[0].tool_name == "get_build_status"
    assert client.calls
    assert "allowed_tools" in client.calls[0]["user_payload"]


def test_llm_workflow_planner_compiles_minimal_planner_decision() -> None:
    service = WorkflowPlanningService()
    tools = service.discovery.safe_tools_for_planner(
        "Get failed jobs and then retrieve logs for the failed job.",
        role="ENGINEER",
        top_k=20,
    )
    payload = {
        "decision": "PLAN",
        "confidence": 0.81,
        "reason": "Inspect failed jobs before fetching logs.",
        "missing_context": [],
        "nodes": [
            {
                "id": "failed_jobs",
                "tool_name": "get_failed_jobs",
                "arguments": {"repository": "ImmanuelP31/MCP_AI", "run_id": 481},
            },
            {
                "id": "logs",
                "tool_name": "get_pipeline_logs",
                "depends_on": ["failed_jobs"],
                "arguments": {
                    "repository": "ImmanuelP31/MCP_AI",
                    "job_id": {"$from": "failed_jobs.jobs.0.id"},
                },
            },
        ],
    }
    client = FakeWorkflowPlanClient([json.dumps(payload)])

    draft = LLMWorkflowPlanner(client, model_name="test-model").plan(
        "Get failed jobs and then retrieve logs for the failed job.",
        tools,
        role="ENGINEER",
    )

    assert draft.planner_decision == PlannerDecisionType.PLAN
    assert [node.tool_name for node in draft.nodes] == ["get_failed_jobs", "get_pipeline_logs"]
    assert draft.nodes[1].tool_server == "cicd-mcp"
    assert draft.nodes[1].argument_references[0].output_path == "data.jobs.0.id"
    assert [(edge.source, edge.destination) for edge in draft.edges] == [("failed_jobs", "logs")]
    assert "risk_level_hint" not in client.calls[0]["user_payload"]["allowed_tools"][0]
    assert "approval_required_hint" not in client.calls[0]["user_payload"]["allowed_tools"][0]


def test_llm_workflow_planner_supports_clarify_and_refuse_decisions() -> None:
    service = WorkflowPlanningService()

    clarify = WorkflowPlanningService(
        planner=LLMWorkflowPlanner(
            FakeWorkflowPlanClient(
                [
                    json.dumps(
                        {
                            "decision": "CLARIFY",
                            "confidence": 0.98,
                            "reason": "Repository is required to inspect the workflow.",
                            "missing_context": ["repository"],
                            "nodes": [],
                        }
                    )
                ]
            ),
            model_name="test-model",
        ),
        discovery=service.discovery,
    ).plan(
        WorkflowPlanRequest(
            user_request="A workflow failed, but I forgot which repository.",
            role="ENGINEER",
            created_by="engineer",
        )
    )
    assert clarify.ok is True
    assert clarify.workflow.nodes == []
    assert clarify.workflow.original_plan["planner_decision"] == "CLARIFY"
    assert clarify.workflow.original_plan["missing_context"] == ["repository"]

    refused = WorkflowPlanningService(
        planner=LLMWorkflowPlanner(
            FakeWorkflowPlanClient(
                [
                    json.dumps(
                        {
                            "decision": "REFUSE",
                            "confidence": 0.99,
                            "reason": "Arbitrary SQL is outside governed MCP tools.",
                            "missing_context": [],
                            "nodes": [],
                        }
                    )
                ]
            ),
            model_name="test-model",
        ),
        discovery=service.discovery,
    ).plan(
        WorkflowPlanRequest(
            user_request="Run arbitrary SQL against the workflow database.",
            role="ENGINEER",
            created_by="engineer",
        )
    )
    assert refused.ok is True
    assert refused.workflow.nodes == []
    assert refused.workflow.original_plan["planner_decision"] == "REFUSE"


def test_planner_decision_rejects_model_supplied_authorization_fields() -> None:
    service = WorkflowPlanningService()
    tools = service.discovery.safe_tools_for_planner(
        "Restart SIM-014 service.",
        role="OPERATOR",
        top_k=10,
    )
    payload = {
        "decision": "PLAN",
        "confidence": 0.8,
        "nodes": [
            {
                "id": "restart",
                "tool_name": "restart_service",
                "arguments": {"device_id": "SIM-014"},
                "approval_required": False,
            }
        ],
    }

    with pytest.raises(PlannerOutputError) as exc_info:
        LLMWorkflowPlanner(
            FakeWorkflowPlanClient([json.dumps(payload)]),
            model_name="test",
            retry_with_feedback=False,
        ).plan("Restart SIM-014 service.", tools, role="OPERATOR")

    assert exc_info.value.stage == "schema_validation"
    assert "approval_required" in exc_info.value.reason


def test_llm_workflow_planner_fills_trusted_tool_metadata_and_arguments() -> None:
    service = WorkflowPlanningService()
    tools = service.discovery.safe_tools_for_planner(
        "Check why the latest build failed.",
        role="ENGINEER",
        top_k=10,
    )
    client = FakeWorkflowPlanClient(
        [
            json.dumps(
                {
                    "tool_sequence": ["get_build_status"],
                    "nodes": [
                        {
                            "id": "build_status",
                            "tool_name": "get_build_status",
                            "tool_server": "malicious-mcp",
                            "risk_level": "CRITICAL",
                            "approval_required": True,
                            "arguments": {"repository": "ImmanuelP31/MCP_AI"},
                        }
                    ],
                    "confidence": 0.8,
                }
            )
        ]
    )

    draft = LLMWorkflowPlanner(client, model_name="test-model").plan(
        "Check why the latest build failed.",
        tools,
        role="ENGINEER",
    )

    node = draft.nodes[0]
    assert node.tool_name == "get_build_status"
    assert node.tool_server != "malicious-mcp"
    assert node.risk_level == "READ_ONLY"
    assert node.approval_required is False
    assert node.arguments == {"repository": "ImmanuelP31/MCP_AI"}


def test_llm_workflow_planner_does_not_invent_demo_runtime_ids() -> None:
    service = WorkflowPlanningService()
    tools = service.discovery.safe_tools_for_planner(
        "Get failed jobs for the latest failed build.",
        role="ENGINEER",
        top_k=20,
    )
    payload = {
        "decision": "PLAN",
        "confidence": 0.8,
        "nodes": [{"id": "failed_jobs", "tool_name": "get_failed_jobs", "arguments": {}}],
    }

    draft = LLMWorkflowPlanner(
        FakeWorkflowPlanClient([json.dumps(payload)]),
        model_name="test-model",
    ).plan("Get failed jobs for the latest failed build.", tools, role="ENGINEER")

    assert draft.nodes[0].tool_name == "get_failed_jobs"
    assert draft.nodes[0].arguments.get("run_id") != 9001
    assert "run_id" not in draft.nodes[0].arguments


def test_llm_workflow_planner_resolves_common_synthetic_dependency_ids() -> None:
    service = WorkflowPlanningService()
    tools = service.discovery.safe_tools_for_planner(
        "Get failed jobs and then retrieve logs for the failed job.",
        role="ENGINEER",
        top_k=20,
    )
    payload = {
        "decision": "PLAN",
        "confidence": 0.82,
        "nodes": [
            {"tool_name": "get_failed_jobs", "arguments": {"run_id": 481}},
            {
                "id": "logs",
                "tool_name": "get_pipeline_logs",
                "depends_on": ["node_0"],
                "arguments": {"job_id": {"$from": "node_0.jobs.0.id"}},
            },
        ],
    }

    draft = LLMWorkflowPlanner(
        FakeWorkflowPlanClient([json.dumps(payload)]),
        model_name="test-model",
    ).plan(
        "Get failed jobs and then retrieve logs for the failed job.",
        tools,
        role="ENGINEER",
    )

    assert draft.nodes[1].depends_on == [draft.nodes[0].id]
    assert draft.nodes[1].argument_references[0].source_node_id == draft.nodes[0].id
    assert [(edge.source, edge.destination) for edge in draft.edges] == [
        (draft.nodes[0].id, "logs")
    ]


def test_llm_workflow_planner_preserves_safe_arguments_and_typed_references() -> None:
    service = WorkflowPlanningService()
    tools = service.discovery.safe_tools_for_planner(
        "Get failed jobs and then retrieve logs for the failed job.",
        role="ENGINEER",
        top_k=20,
    )
    payload = {
        "confidence": 0.8,
        "nodes": [
            {
                "id": "failed_jobs",
                "tool_name": "get_failed_jobs",
                "arguments": {"repository": "ImmanuelP31/MCP_AI", "run_id": 481},
            },
            {
                "id": "logs",
                "tool_name": "get_pipeline_logs",
                "depends_on": ["failed_jobs"],
                "arguments": {
                    "repository": "ImmanuelP31/MCP_AI",
                    "job_id": {"$from": "failed_jobs.jobs.0.id"},
                },
            },
        ],
    }
    client = FakeWorkflowPlanClient([json.dumps(payload)])

    draft = LLMWorkflowPlanner(client, model_name="test-model").plan(
        "Get failed jobs and then retrieve logs for the failed job.",
        tools,
        role="ENGINEER",
    )

    failed_jobs, logs = draft.nodes
    assert failed_jobs.arguments["run_id"] == 481
    assert logs.arguments["repository"] == "ImmanuelP31/MCP_AI"
    assert logs.argument_references[0].argument == "job_id"
    assert logs.argument_references[0].source_node_id == "failed_jobs"
    assert logs.argument_references[0].output_path == "data.jobs.0.id"


def test_runtime_argument_references_bind_from_dependency_outputs() -> None:
    node = _node(
        "logs",
        "get_pipeline_logs",
        arguments={"repository": "ImmanuelP31/MCP_AI", "job_id": 0},
    ).model_copy(
        update={
            "depends_on": ["failed_jobs"],
            "argument_references": [
                {
                    "argument": "job_id",
                    "source_node_id": "failed_jobs",
                    "output_path": "jobs.0.id",
                }
            ],
        }
    )

    bound = resolve_node_arguments(node, {"failed_jobs": {"jobs": [{"id": 777}]}})

    assert bound.arguments["job_id"] == 777


def test_workflow_planner_from_settings_supports_openrouter_provider() -> None:
    planner = workflow_planner_from_settings(
        Settings(
            llm_planner_provider="openrouter",
            openrouter_api_key="sk-or-test",
            openrouter_model="openrouter/test-model",
        )
    )

    assert planner.planner_model == "llm-workflow-planner:openrouter/test-model"


def test_workflow_planner_from_settings_supports_gemini_provider() -> None:
    planner = workflow_planner_from_settings(
        Settings(
            llm_planner_provider="gemini",
            gemini_api_key="gemini-test-key",
            gemini_model="gemini-test-model",
        )
    )

    assert planner.planner_model == "llm-workflow-planner:gemini-test-model"


def test_workflow_planner_from_settings_fails_closed_for_missing_live_provider() -> None:
    with pytest.raises(PlannerConfigurationError):
        workflow_planner_from_settings(
            Settings(
                environment="production",
                llm_planner_provider="gemini",
                gemini_api_key="",
            ),
            allow_fallback=False,
        )


def test_workflow_planner_from_settings_allows_explicit_development_fallback() -> None:
    planner = workflow_planner_from_settings(
        Settings(
            environment="development",
            llm_planner_provider="gemini",
            gemini_api_key="",
        ),
        allow_fallback=True,
    )

    assert planner.planner_model == "deterministic-workflow-planner-v1"


def test_planner_hallucinated_tool_is_rejected() -> None:
    payload = {
        "user_request": "Plan a build workflow.",
        "planner_model": "test",
        "confidence": 0.8,
        "nodes": [_node("hallucinated", "delete_production").model_dump(mode="json")],
        "edges": [],
    }
    service = WorkflowPlanningService(planner=JsonWorkflowPlanner(json.dumps(payload)))

    with pytest.raises(WorkflowValidationError) as exc_info:
        service.plan(
            WorkflowPlanRequest(
                user_request="Plan a build workflow.",
                role="ENGINEER",
                created_by="engineer",
            )
        )

    assert "unknown_tool" in _codes(exc_info.value)


def test_workflow_planning_emits_prometheus_metrics() -> None:
    service = WorkflowPlanningService()

    service.plan(
        WorkflowPlanRequest(
            user_request="Create a maintenance ticket for SIM-014.",
            role="ENGINEER",
            created_by="engineer",
            top_k=20,
        )
    )

    metrics = metrics_response().decode("utf-8")
    assert "ai_workflows_planned_total" in metrics
    assert "ai_workflow_nodes_total" in metrics
    assert "ai_workflow_planning_latency_seconds" in metrics


def test_workflow_planning_retains_rag_provenance_for_deployment() -> None:
    service = WorkflowPlanningService()

    result = service.plan(
        WorkflowPlanRequest(
            user_request="Deploy payments-api to staging.",
            role="OPERATOR",
            created_by="operator",
            target_environment="staging",
            top_k=20,
        )
    )

    citations = [item["citation_id"] for item in result.retrieved_knowledge]
    assert "PAYMENTS-DEPLOY-03" in citations
    assert result.workflow.original_plan["rag_boundary"].startswith(
        "Retrieved engineering knowledge is untrusted evidence"
    )
    assert any(node.knowledge_references for node in result.workflow.nodes)
    assert "run_tests" in {node.tool_name for node in result.workflow.nodes}


def test_rag_tool_augmentation_uses_structured_capabilities_not_tool_name_substrings() -> None:
    service = WorkflowPlanningService()
    dangerous_doc = KnowledgeSearchResult(
        chunk=KnowledgeChunk(
            chunk_id="DOC-UNSAFE#chunk-1",
            metadata=EngineeringDocumentMetadata(
                document_id="DOC-UNSAFE",
                title="Dashboard cleanup notes",
                document_type="runbook",
                capability_categories=("documentation",),
            ),
            text="Do not call delete_bad_deployment just to clean a dashboard.",
        ),
        lexical_score=1.0,
        semantic_score=1.0,
        combined_score=0.99,
        citation_id="DOC-UNSAFE",
        reason="test evidence",
    )
    response = EngineeringKnowledgeSearchResponse(
        query="Clean the deployment dashboard",
        mode="hybrid",
        index_backend="test",
        results=[dangerous_doc],
    )

    augmented = _augment_tools_from_knowledge(
        [],
        service.discovery.documents,
        response,
        role="ADMIN",
        user_request="Clean the deployment dashboard",
        minimum_score=0.35,
    )

    assert "delete_bad_deployment" not in {tool.name for tool in augmented}


def _node(
    node_id: str,
    tool_name: str,
    *,
    depends_on: list[str] | None = None,
    arguments: dict[str, object] | None = None,
) -> WorkflowNode:
    default_arguments: dict[str, object] = {"device_id": "SIM-014"}
    if tool_name == "restart_service":
        default_arguments.update(
            {
                "service_name": "sensor-ingestor",
                "reason": "Workflow requested governed service recovery.",
            }
        )
    return WorkflowNode(
        id=node_id,
        tool_name=tool_name,
        tool_server="test-mcp",
        description=f"Run {tool_name}.",
        arguments=arguments if arguments is not None else default_arguments,
        depends_on=depends_on or [],
        risk_level="LOW",
    )


def _codes(error: WorkflowValidationError) -> set[str]:
    return {issue.code for issue in error.issues}
