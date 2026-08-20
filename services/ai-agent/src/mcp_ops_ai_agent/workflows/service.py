from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from mcp_ops_mcp_gateway.models import GatewayDecision, GatewayToolRequest, GatewayToolResponse
from mcp_ops_observability.metrics import (
    record_workflow_compensation,
    record_workflow_execution,
    record_workflow_execution_failure,
    record_workflow_plan_failure,
    record_workflow_planned,
    record_workflow_recovery_success,
    record_workflow_retry,
    record_workflow_validation_failure,
)
from mcp_ops_policy.tool_registry import TOOL_REGISTRY

from mcp_ops_ai_agent.capabilities.service import CapabilityGraphService
from mcp_ops_ai_agent.engineering_rag import EngineeringRagService
from mcp_ops_ai_agent.engineering_rag.models import (
    EngineeringKnowledgeSearchRequest,
    EngineeringKnowledgeSearchResponse,
    KnowledgeFilters,
    KnowledgeSearchMode,
)
from mcp_ops_ai_agent.gateway import GatewayClient, gateway_client_from_settings
from mcp_ops_ai_agent.tool_discovery import ToolDiscoveryService
from mcp_ops_ai_agent.tool_discovery.models import ToolDocument
from mcp_ops_ai_agent.workflows.arguments import (
    ArgumentBindingError,
    normalize_tool_output,
    resolve_node_arguments,
)
from mcp_ops_ai_agent.workflows.conditions import (
    ConditionEvaluationError,
    condition_is_satisfied,
)
from mcp_ops_ai_agent.workflows.events import (
    InMemoryWorkflowEventPublisher,
    WorkflowEventPublisher,
)
from mcp_ops_ai_agent.workflows.models import (
    PolicyDecision,
    RetryStrategy,
    Workflow,
    WorkflowAuditEvent,
    WorkflowNode,
    WorkflowNodeStatus,
    WorkflowPlanDraft,
    WorkflowPlanRequest,
    WorkflowPlanResult,
    WorkflowStatus,
)
from mcp_ops_ai_agent.workflows.planner import (
    DeterministicWorkflowPlanner,
    PlannerOutputError,
    WorkflowPlanner,
)
from mcp_ops_ai_agent.workflows.policy import WorkflowPolicyEvaluator, transform_node_with_policy
from mcp_ops_ai_agent.workflows.repository import (
    InMemoryWorkflowRepository,
    WorkflowRepositoryProtocol,
)
from mcp_ops_ai_agent.workflows.validator import WorkflowValidationError, WorkflowValidator


class WorkflowNotFoundError(KeyError):
    pass


class WorkflowPlanningService:
    """Policy-aware workflow planner and executor for engineering DAGs."""

    def __init__(
        self,
        *,
        discovery: ToolDiscoveryService | None = None,
        planner: WorkflowPlanner | None = None,
        validator: WorkflowValidator | None = None,
        policy_evaluator: WorkflowPolicyEvaluator | None = None,
        capability_graph: CapabilityGraphService | None = None,
        rag: EngineeringRagService | None = None,
        use_rag: bool = True,
        use_capability_graph: bool = True,
        repository: WorkflowRepositoryProtocol | None = None,
        gateway_client: GatewayClient | None = None,
        event_publisher: WorkflowEventPublisher | None = None,
    ) -> None:
        self.discovery = discovery or ToolDiscoveryService()
        self.planner = planner or DeterministicWorkflowPlanner()
        self.validator = validator or WorkflowValidator()
        self.policy_evaluator = policy_evaluator or WorkflowPolicyEvaluator()
        self.capability_graph = capability_graph or CapabilityGraphService(
            policy_evaluator=self.policy_evaluator
        )
        self.rag = rag or EngineeringRagService()
        self.use_rag = use_rag
        self.use_capability_graph = use_capability_graph
        self.repository = repository or InMemoryWorkflowRepository()
        self.gateway_client = gateway_client or gateway_client_from_settings()
        self.event_publisher = event_publisher or InMemoryWorkflowEventPublisher()

    def plan(self, request: WorkflowPlanRequest) -> WorkflowPlanResult:
        started = time.perf_counter()
        planner_model = self.planner.planner_model
        try:
            discovery_response = self.discovery.retrieve(
                request.user_request,
                role=request.role,
                top_k=request.top_k,
            )
            discovered_tools = [result.tool for result in discovery_response.ranked_tools]
            knowledge_response = (
                self.rag.search(
                    EngineeringKnowledgeSearchRequest(
                        query=request.user_request,
                        top_k=5,
                        filters=KnowledgeFilters(environment=request.target_environment),
                    )
                )
                if self.use_rag
                else EngineeringKnowledgeSearchResponse(
                    query=request.user_request,
                    mode=KnowledgeSearchMode.HYBRID.value,
                    index_backend="disabled",
                    results=[],
                )
            )
            if self.use_rag:
                discovered_tools = _augment_tools_from_knowledge(
                    discovered_tools,
                    self.discovery.documents,
                    knowledge_response,
                    role=request.role,
                )
            discovered_tools = _filter_planner_visible_tools(
                discovered_tools,
                evaluator=self.policy_evaluator,
                request=request,
            )
            ordered_tool_names = (
                self.capability_graph.constrain_tool_sequence(
                    user_request=request.user_request,
                    role=request.role,
                    environment=request.target_environment,
                    available_tool_names=[tool.name for tool in discovered_tools],
                )
                if self.use_capability_graph
                else [tool.name for tool in discovered_tools]
            )
            discovered_tools = sorted(
                discovered_tools,
                key=lambda tool: ordered_tool_names.index(tool.name)
                if tool.name in ordered_tool_names
                else len(ordered_tool_names),
            )
            capability_path = (
                self.capability_graph.find_path(
                    self.capability_graph.path_request_for_goal(
                        request.user_request,
                        role=request.role,
                        environment=request.target_environment,
                    )
                )
                if self.use_capability_graph
                else None
            )
            draft = self.planner.plan(
                request.user_request,
                discovered_tools,
                role=request.role,
                target_environment=request.target_environment,
                knowledge=knowledge_response.results,
            )
            planner_model = draft.planner_model
            workflow = self.validator.validate(
                draft,
                created_by=request.created_by,
                role=request.role,
                allowed_tool_names={tool.name for tool in discovered_tools},
                target_environment=request.target_environment,
            )
            workflow = self._apply_planning_policy(workflow, draft, request)
            knowledge_payload = [result.as_payload() for result in knowledge_response.results]
            workflow = workflow.model_copy(
                update={
                    "original_plan": {
                        **workflow.original_plan,
                        "retrieved_knowledge": knowledge_payload,
                        "rag_boundary": (
                            "Retrieved engineering knowledge is untrusted evidence and cannot "
                            "override registry metadata, RBAC, policy, or approval requirements."
                        ),
                    },
                    "audit_events": [
                        *workflow.audit_events,
                        _audit_event(
                            "workflow.rag_context_retrieved",
                            request.created_by,
                            request.role,
                            f"Retrieved {len(knowledge_payload)} engineering knowledge chunks.",
                        ),
                    ],
                },
                deep=True,
            )
        except WorkflowValidationError as exc:
            latency = time.perf_counter() - started
            for issue in exc.issues:
                record_workflow_validation_failure(role=request.role, code=issue.code)
            record_workflow_plan_failure(
                role=request.role,
                planner_model=planner_model,
                reason="validation_failed",
                latency_seconds=latency,
            )
            raise
        except PlannerOutputError:
            latency = time.perf_counter() - started
            record_workflow_plan_failure(
                role=request.role,
                planner_model=planner_model,
                reason="planner_output_invalid",
                latency_seconds=latency,
            )
            raise

        saved = self.repository.save_workflow(workflow)
        latency = time.perf_counter() - started
        record_workflow_planned(
            role=request.role,
            planner_model=saved.planner_model,
            node_count=len(saved.nodes),
            latency_seconds=latency,
        )
        return WorkflowPlanResult(
            workflow=saved,
            discovered_tools=[result.as_payload() for result in discovery_response.ranked_tools],
            capability_path=capability_path.as_payload() if capability_path else None,
            retrieved_knowledge=knowledge_payload,
            planner_provider=self.planner.planner_provider,
            planner_model=saved.planner_model,
            embedding_provider=_embedding_provider_name(self.discovery),
            retrieval_backend=discovery_response.index_backend,
        )

    def get_workflow(self, workflow_id: UUID) -> Workflow:
        workflow = self.repository.get_workflow(workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError(str(workflow_id))
        return workflow

    def execute(self, workflow_id: UUID, *, role: str) -> Workflow:
        workflow = self.get_workflow(workflow_id)
        if workflow.status == WorkflowStatus.CANCELLED:
            return workflow
        if workflow.status == WorkflowStatus.WAITING_APPROVAL:
            return workflow
        return self._run_workflow(workflow, role=role, resumed=False)

    def resume(self, workflow_id: UUID, *, role: str) -> Workflow:
        workflow = self.get_workflow(workflow_id)
        if workflow.status == WorkflowStatus.CANCELLED:
            return workflow
        resumable = {
            WorkflowNodeStatus.FAILED,
            WorkflowNodeStatus.BLOCKED,
            WorkflowNodeStatus.RETRYING,
            WorkflowNodeStatus.RUNNING,
        }
        nodes = [
            _expire_waiting_approval(node)
            if _approval_expired(node)
            else node.model_copy(update={"execution_status": WorkflowNodeStatus.PENDING})
            if node.execution_status in resumable and _can_be_resumed(node)
            else node
            for node in workflow.nodes
        ]
        resumed_workflow = workflow.model_copy(
            update={
                "status": WorkflowStatus.RUNNING,
                "version": workflow.version + 1,
                "nodes": nodes,
                "audit_events": [
                    *workflow.audit_events,
                    _audit_event(
                        "workflow.resume_requested",
                        workflow.created_by,
                        role,
                        "Workflow resume requested from persisted checkpoint.",
                    ),
                ],
            },
            deep=True,
        )
        saved = self.repository.save_workflow(resumed_workflow)
        result = self._run_workflow(saved, role=role, resumed=True)
        if result.status in {WorkflowStatus.COMPLETED, WorkflowStatus.WAITING_APPROVAL}:
            record_workflow_recovery_success(role=role)
        return result

    def retry_node(self, workflow_id: UUID, node_id: str, *, role: str) -> Workflow:
        workflow = self.get_workflow(workflow_id)
        nodes = []
        found = False
        for node in workflow.nodes:
            if node.id != node_id:
                nodes.append(node)
                continue
            found = True
            metadata = TOOL_REGISTRY.get(node.tool_name)
            if not _metadata_retryable(metadata):
                nodes.append(
                    node.model_copy(
                        update={
                            "execution_status": WorkflowNodeStatus.FAILED,
                            "last_error": "manual retry denied for non-idempotent tool",
                        }
                    )
                )
                continue
            nodes.append(
                node.model_copy(
                    update={
                        "execution_status": WorkflowNodeStatus.PENDING,
                        "last_error": None,
                        "next_retry_at": None,
                    }
                )
            )
        if not found:
            raise WorkflowNotFoundError(f"{workflow_id}:{node_id}")
        updated = workflow.model_copy(
            update={
                "status": WorkflowStatus.RUNNING,
                "version": workflow.version + 1,
                "nodes": nodes,
                "audit_events": [
                    *workflow.audit_events,
                    _audit_event(
                        "workflow.node.retry_requested",
                        workflow.created_by,
                        role,
                        f"Manual retry requested for node {node_id}.",
                        node_id,
                    ),
                ],
            },
            deep=True,
        )
        return self._run_workflow(self.repository.save_workflow(updated), role=role, resumed=True)

    def _run_workflow(self, workflow: Workflow, *, role: str, resumed: bool) -> Workflow:
        started = time.perf_counter()
        updated = workflow.model_copy(
            update={
                "status": WorkflowStatus.RUNNING,
                "version": workflow.version + 1,
                "audit_events": [
                    *workflow.audit_events,
                    _audit_event(
                        "workflow.resumed" if resumed else "workflow.started",
                        workflow.created_by,
                        role,
                        "Workflow execution started from persisted state.",
                    ),
                ],
            },
            deep=True,
        )
        updated = self._checkpoint(updated, "workflow.started")
        nodes_by_id = {node.id: node for node in updated.nodes}
        node_outputs: dict[str, dict[str, Any]] = {
            node.id: {"result_reference": node.result_reference}
            for node in updated.nodes
            if node.execution_status
            in {
                WorkflowNodeStatus.SUCCEEDED,
                WorkflowNodeStatus.COMPENSATED,
                WorkflowNodeStatus.SKIPPED,
            }
            and node.result_reference is not None
        }
        completed: set[str] = {
            node.id
            for node in updated.nodes
            if node.execution_status
            in {
                WorkflowNodeStatus.SUCCEEDED,
                WorkflowNodeStatus.COMPENSATED,
                WorkflowNodeStatus.SKIPPED,
            }
        }
        for node in _topological_nodes(updated.nodes):
            if (
                node.execution_status == WorkflowNodeStatus.RETRYING
                and not _retry_due(node)
            ):
                return updated
            if node.execution_status in {
                WorkflowNodeStatus.SUCCEEDED,
                WorkflowNodeStatus.COMPENSATED,
                WorkflowNodeStatus.SKIPPED,
                WorkflowNodeStatus.CANCELLED,
                WorkflowNodeStatus.FAILED,
                WorkflowNodeStatus.DENIED,
                WorkflowNodeStatus.BLOCKED,
            }:
                continue
            if not set(node.depends_on).issubset(completed):
                nodes_by_id[node.id] = node.model_copy(
                    update={"execution_status": WorkflowNodeStatus.BLOCKED}
                )
                updated = self._replace_nodes(updated, nodes_by_id)
                updated = self._checkpoint(updated, "workflow.node.blocked", node_id=node.id)
                continue
            try:
                condition_result = condition_is_satisfied(node, node_outputs)
            except ConditionEvaluationError as exc:
                nodes_by_id[node.id] = node.model_copy(
                    update={
                        "execution_status": WorkflowNodeStatus.BLOCKED,
                        "last_error": f"condition evaluation failed: {exc}",
                    }
                )
                updated = self._replace_nodes(updated, nodes_by_id)
                updated = self._checkpoint(updated, "workflow.node.failed", node_id=node.id)
                record_workflow_execution_failure(role=role, reason="condition_evaluation_failed")
                return self._finish_workflow(updated, role, started)
            if not condition_result:
                nodes_by_id[node.id] = node.model_copy(
                    update={"execution_status": WorkflowNodeStatus.SKIPPED}
                )
                updated = self._replace_nodes(updated, nodes_by_id)
                updated = self._checkpoint(updated, "workflow.node.skipped", node_id=node.id)
                continue
            metadata = TOOL_REGISTRY.get(node.tool_name)
            ready_node = node.model_copy(update={"execution_status": WorkflowNodeStatus.READY})
            nodes_by_id[node.id] = ready_node
            updated = self._replace_nodes(updated, nodes_by_id)
            updated = self._checkpoint(updated, "workflow.node.ready", node_id=node.id)
            evaluation = self.policy_evaluator.evaluate(
                ready_node,
                actor=workflow.created_by,
                role=role,
                environment=workflow.target_environment,
                phase="execution",
            )
            policy_node = transform_node_with_policy(ready_node, evaluation, metadata)
            nodes_by_id[node.id] = policy_node
            updated = self._replace_nodes(updated, nodes_by_id)
            updated = self._checkpoint(updated, "workflow.node.policy_evaluated", node_id=node.id)
            if evaluation.decision == PolicyDecision.DENY:
                nodes_by_id[node.id] = policy_node.model_copy(
                    update={
                        "execution_status": WorkflowNodeStatus.DENIED,
                        "last_error": evaluation.reason,
                        "completed_at": datetime.now(UTC),
                    }
                )
                updated = self._replace_nodes(updated, nodes_by_id)
                updated = self._checkpoint(updated, "workflow.node.failed", node_id=node.id)
                record_workflow_execution_failure(role=role, reason="policy_denied")
                continue
            if evaluation.decision == PolicyDecision.REQUIRE_ADDITIONAL_CONTEXT:
                nodes_by_id[node.id] = policy_node.model_copy(
                    update={
                        "execution_status": WorkflowNodeStatus.BLOCKED,
                        "last_error": evaluation.reason,
                    }
                )
                updated = self._replace_nodes(updated, nodes_by_id)
                updated = self._checkpoint(updated, "workflow.node.failed", node_id=node.id)
                record_workflow_execution_failure(role=role, reason="additional_context_required")
                continue
            outcome = self._execute_node_with_recovery(
                policy_node,
                role,
                updated,
                nodes_by_id,
                node_outputs,
            )
            updated = outcome
            nodes_by_id = {item.id: item for item in updated.nodes}
            latest = nodes_by_id[node.id]
            if latest.execution_status == WorkflowNodeStatus.WAITING_APPROVAL:
                record_workflow_execution(
                    role=role,
                    outcome="waiting_approval",
                    duration_seconds=time.perf_counter() - started,
                )
                return updated
            if latest.execution_status == WorkflowNodeStatus.RETRYING:
                return updated
            if latest.execution_status in {WorkflowNodeStatus.FAILED, WorkflowNodeStatus.BLOCKED}:
                record_workflow_execution_failure(role=role, reason=latest.last_error or "failed")
                return self._finish_workflow(updated, role, started)
            completed.add(node.id)
        return self._finish_workflow(updated, role, started)

    def _execute_node_with_recovery(
        self,
        node: WorkflowNode,
        role: str,
        workflow: Workflow,
        nodes_by_id: dict[str, WorkflowNode],
        node_outputs: dict[str, dict[str, Any]],
    ) -> Workflow:
        current = workflow
        while True:
            attempt_started = datetime.now(UTC)
            running_node = node.model_copy(
                update={
                    "execution_status": WorkflowNodeStatus.RUNNING,
                    "attempts": node.attempts + 1,
                    "started_at": node.started_at or attempt_started,
                    "last_attempt_at": attempt_started,
                    "last_error": None,
                }
            )
            nodes_by_id[node.id] = running_node
            current = self._replace_nodes(current, nodes_by_id)
            current = self._checkpoint(current, "workflow.node.started", node_id=node.id)
            try:
                bound_node = resolve_node_arguments(running_node, node_outputs)
                if bound_node.arguments != running_node.arguments:
                    nodes_by_id[node.id] = bound_node
                    current = self._replace_nodes(current, nodes_by_id)
                    current = self._checkpoint(
                        current,
                        "workflow.node.arguments_bound",
                        node_id=node.id,
                    )
                    running_node = bound_node
                response = self._execute_node(running_node, role)
            except ArgumentBindingError as exc:
                response = _failure_response(running_node, "argument_binding_failed", str(exc))
            except TimeoutError as exc:
                response = _failure_response(running_node, "timeout", str(exc))
            except ConnectionError as exc:
                response = _failure_response(running_node, "network_failure", str(exc))
            except RuntimeError as exc:
                response = _failure_response(running_node, "tool_server_unavailable", str(exc))
            result_ref = str(response.correlation_id)
            if response.decision == GatewayDecision.PENDING_APPROVAL:
                approval_id = response.data.get("approval_id")
                waiting_node = running_node.model_copy(
                    update={
                        "execution_status": WorkflowNodeStatus.WAITING_APPROVAL,
                        "result_reference": str(approval_id or result_ref),
                    }
                )
                nodes_by_id[node.id] = waiting_node
                current = self._replace_nodes(
                    current.model_copy(
                        update={
                            "status": WorkflowStatus.WAITING_APPROVAL,
                            "audit_events": [
                                *current.audit_events,
                                _audit_event(
                                    "workflow.approval_requested",
                                    current.created_by,
                                    role,
                                    f"Approval requested for {node.tool_name}.",
                                    node.id,
                                ),
                            ],
                        },
                        deep=True,
                    ),
                    nodes_by_id,
                )
                return self._checkpoint(
                    current,
                    "workflow.approval.required",
                    node_id=node.id,
                )
            if response.ok and isinstance(response.data, dict):
                node_outputs[node.id] = normalize_tool_output(dict(response.data))
                succeeded_node = running_node.model_copy(
                    update={
                        "execution_status": WorkflowNodeStatus.SUCCEEDED,
                        "result_reference": result_ref,
                        "completed_at": datetime.now(UTC),
                    }
                )
                nodes_by_id[node.id] = succeeded_node
                current = self._replace_nodes(current, nodes_by_id)
                return self._checkpoint(current, "workflow.node.succeeded", node_id=node.id)
            failed_node = running_node.model_copy(
                update={
                    "execution_status": WorkflowNodeStatus.FAILED,
                    "result_reference": result_ref,
                    "last_error": _response_error(response),
                    "completed_at": datetime.now(UTC),
                }
            )
            nodes_by_id[node.id] = failed_node
            current = self._replace_nodes(current, nodes_by_id)
            current = self._checkpoint(current, "workflow.node.failed", node_id=node.id)
            metadata = TOOL_REGISTRY.get(failed_node.tool_name)
            if _transient_failure(response) and _retry_allowed(failed_node, metadata):
                retry_node = failed_node.model_copy(
                    update={
                        "execution_status": WorkflowNodeStatus.RETRYING,
                        "next_retry_at": _next_retry_time(failed_node),
                        "completed_at": None,
                    }
                )
                nodes_by_id[node.id] = retry_node
                current = self._replace_nodes(current, nodes_by_id)
                current = self._checkpoint(current, "workflow.node.retrying", node_id=node.id)
                record_workflow_retry(
                    role=role,
                    tool_name=node.tool_name,
                    strategy=retry_node.retry_strategy.value,
                )
                node = retry_node
                return current
            if failed_node.compensation_tool:
                return self._compensate_node(failed_node, role, current, nodes_by_id)
            return current

    def _compensate_node(
        self,
        node: WorkflowNode,
        role: str,
        workflow: Workflow,
        nodes_by_id: dict[str, WorkflowNode],
    ) -> Workflow:
        compensating = node.model_copy(update={"execution_status": WorkflowNodeStatus.COMPENSATING})
        nodes_by_id[node.id] = compensating
        current = self._replace_nodes(workflow, nodes_by_id)
        current = self._checkpoint(current, "workflow.compensation.started", node_id=node.id)
        compensation_request = compensating.model_copy(
            update={
                "tool_name": compensating.compensation_tool,
                "arguments": {
                    "workflow_id": str(workflow.id),
                    "failed_node_id": node.id,
                    "result_reference": node.result_reference or "",
                },
            }
        )
        response = self._execute_node(compensation_request, role)
        if response.ok:
            compensated = compensating.model_copy(
                update={
                    "execution_status": WorkflowNodeStatus.COMPENSATED,
                    "completed_at": datetime.now(UTC),
                    "last_error": None,
                }
            )
            outcome = "ok"
        else:
            compensated = compensating.model_copy(
                update={
                    "execution_status": WorkflowNodeStatus.FAILED,
                    "last_error": _response_error(response),
                    "completed_at": datetime.now(UTC),
                }
            )
            outcome = "failed"
        nodes_by_id[node.id] = compensated
        record_workflow_compensation(role=role, tool_name=node.tool_name, outcome=outcome)
        current = self._replace_nodes(current, nodes_by_id)
        return self._checkpoint(current, "workflow.compensation.completed", node_id=node.id)

    def _finish_workflow(self, workflow: Workflow, role: str, started: float) -> Workflow:
        final_nodes = workflow.nodes
        final_status = (
            WorkflowStatus.FAILED
            if any(
                node.execution_status
                in {
                    WorkflowNodeStatus.FAILED,
                    WorkflowNodeStatus.DENIED,
                    WorkflowNodeStatus.BLOCKED,
                }
                for node in final_nodes
            )
            else WorkflowStatus.COMPLETED
        )
        updated = workflow.model_copy(
            update={
                "status": final_status,
                "nodes": final_nodes,
                "audit_events": [
                    *workflow.audit_events,
                    _audit_event(
                        "workflow.execution_finished",
                        workflow.created_by,
                        role,
                        f"Workflow execution finished with status {final_status.value}.",
                    ),
                ],
            },
            deep=True,
        )
        saved = self._checkpoint(updated, "workflow.completed")
        record_workflow_execution(
            role=role,
            outcome=final_status.value.lower(),
            duration_seconds=time.perf_counter() - started,
        )
        return saved

    def _replace_nodes(
        self,
        workflow: Workflow,
        nodes_by_id: dict[str, WorkflowNode],
    ) -> Workflow:
        return workflow.model_copy(
            update={"nodes": [nodes_by_id[node.id] for node in workflow.nodes]},
            deep=True,
        )

    def _checkpoint(
        self,
        workflow: Workflow,
        event_type: str,
        *,
        node_id: str | None = None,
    ) -> Workflow:
        event_payload: dict[str, object] = {
            "workflow_id": str(workflow.id),
            "status": workflow.status.value,
        }
        if node_id is not None:
            event_payload["node_id"] = node_id
        with_event = workflow.model_copy(
            update={"version": workflow.version + 1},
            deep=True,
        )
        try:
            self.event_publisher.publish(event_type, event_payload)
        except Exception as exc:  # noqa: BLE001 - event publishing must not strand execution.
            with_event = with_event.model_copy(
                update={
                    "audit_events": [
                        *with_event.audit_events,
                        _audit_event(
                            "workflow.event_publish_failed",
                            workflow.created_by,
                            "SYSTEM",
                            f"{event_type} publish failed: {exc}",
                            node_id,
                        ),
                    ]
                },
                deep=True,
            )
        return self.repository.save_workflow(with_event)

    def _apply_planning_policy(
        self,
        workflow: Workflow,
        draft: WorkflowPlanDraft,
        request: WorkflowPlanRequest,
    ) -> Workflow:
        proposed = {node.id: node for node in draft.nodes}
        transformed_nodes: list[WorkflowNode] = []
        audit_events = [
            _audit_event(
                "workflow.ai_plan_proposed",
                request.created_by,
                request.role,
                "AI planner proposed a typed workflow DAG.",
            )
        ]
        for node in workflow.nodes:
            metadata = TOOL_REGISTRY.get(node.tool_name)
            evaluation = self.policy_evaluator.evaluate(
                node,
                actor=request.created_by,
                role=request.role,
                environment=request.target_environment,
                phase="planning",
                proposed_node=proposed.get(node.id),
            )
            transformed = transform_node_with_policy(node, evaluation, metadata)
            transformed_nodes.append(transformed)
            if evaluation.decision == PolicyDecision.DENY:
                audit_events.append(
                    _audit_event(
                        "workflow.node_denied",
                        request.created_by,
                        request.role,
                        evaluation.reason,
                        node.id,
                    )
                )
        transformed_workflow = workflow.model_copy(
            update={
                "nodes": transformed_nodes,
                "original_plan": draft.model_dump(mode="json"),
                "audit_events": [
                    *workflow.audit_events,
                    *audit_events,
                    _audit_event(
                        "workflow.policy_transformed",
                        request.created_by,
                        request.role,
                        "Policy transformed the AI plan into an executable workflow.",
                    ),
                ],
            },
            deep=True,
        )
        return transformed_workflow.model_copy(
            update={
                "policy_transformed_plan": transformed_workflow.model_dump(
                    mode="json",
                    exclude={"policy_transformed_plan"},
                )
            },
            deep=True,
        )

    def cancel(self, workflow_id: UUID, *, role: str = "ENGINEER") -> Workflow:
        workflow = self.get_workflow(workflow_id)
        nodes = [
            node.model_copy(update={"execution_status": WorkflowNodeStatus.CANCELLED})
            if node.execution_status
            in {
                WorkflowNodeStatus.PENDING,
                WorkflowNodeStatus.BLOCKED,
                WorkflowNodeStatus.DENIED,
                WorkflowNodeStatus.WAITING_APPROVAL,
                WorkflowNodeStatus.RUNNING,
            }
            else node
            for node in workflow.nodes
        ]
        cancelled = workflow.model_copy(
            update={
                "status": WorkflowStatus.CANCELLED,
                "version": workflow.version + 1,
                "nodes": nodes,
                "audit_events": [
                    *workflow.audit_events,
                    _audit_event(
                        "workflow.cancelled",
                        workflow.created_by,
                        role,
                        "Workflow cancellation requested through API.",
                    ),
                ],
            },
            deep=True,
        )
        return self.repository.save_workflow(cancelled)

    def _execute_node(self, node: WorkflowNode, role: str) -> GatewayToolResponse:
        return self.gateway_client.call_tool(
            GatewayToolRequest(
                auth_token=_role_token(role),
                tool_name=node.tool_name,
                arguments=node.arguments,
                idempotency_key=(
                    f"workflow-{node.workflow_id}-{node.id}-attempt-{max(node.attempts, 1)}"
                ),
                workflow_id=node.workflow_id,
                workflow_node_id=node.id,
            )
        )


def _topological_nodes(nodes: list[WorkflowNode]) -> list[WorkflowNode]:
    ordered: list[WorkflowNode] = []
    remaining = {node.id: node for node in nodes}
    while remaining:
        ready = [
            node
            for node in remaining.values()
            if all(dependency not in remaining for dependency in node.depends_on)
        ]
        if not ready:
            return list(nodes)
        for node in sorted(ready, key=lambda item: item.id):
            ordered.append(node)
            del remaining[node.id]
    return ordered


def _embedding_provider_name(discovery: object) -> str:
    settings = getattr(discovery, "settings", None)
    provider = getattr(settings, "embedding_provider", None)
    if isinstance(provider, str):
        return provider.lower()
    wrapped = getattr(discovery, "wrapped", None)
    wrapped_settings = getattr(wrapped, "settings", None)
    wrapped_provider = getattr(wrapped_settings, "embedding_provider", None)
    if wrapped_settings is not None and isinstance(
        wrapped_provider,
        str,
    ):
        return wrapped_provider.lower()
    return "unknown"


def _can_be_resumed(node: WorkflowNode) -> bool:
    if node.execution_status == WorkflowNodeStatus.RETRYING:
        return _retry_due(node)
    return node.attempts <= node.max_retries or bool(node.compensation_tool)


def _retry_due(node: WorkflowNode) -> bool:
    return node.next_retry_at is None or datetime.now(UTC) >= node.next_retry_at


def _approval_expired(node: WorkflowNode) -> bool:
    if node.execution_status != WorkflowNodeStatus.WAITING_APPROVAL:
        return False
    started = node.last_attempt_at or node.started_at
    if started is None:
        return False
    return datetime.now(UTC) >= started + timedelta(seconds=node.timeout_seconds)


def _expire_waiting_approval(node: WorkflowNode) -> WorkflowNode:
    return node.model_copy(
        update={
            "execution_status": WorkflowNodeStatus.FAILED,
            "last_error": "approval expired before workflow resume",
            "completed_at": datetime.now(UTC),
        }
    )


def _retry_allowed(node: WorkflowNode, metadata: object | None) -> bool:
    if node.retry_strategy == RetryStrategy.NO_RETRY:
        return False
    if node.attempts > node.max_retries:
        return False
    return _metadata_retryable(metadata)


def _metadata_retryable(metadata: object | None) -> bool:
    if metadata is None:
        return False
    idempotent = bool(getattr(metadata, "idempotent", False))
    retry_safe = bool(getattr(metadata, "retry_safe", False))
    return idempotent or retry_safe


def _next_retry_time(node: WorkflowNode) -> datetime:
    if node.retry_strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
        delay_seconds = min(60, 2 ** max(node.attempts - 1, 0))
    elif node.retry_strategy == RetryStrategy.FIXED_DELAY:
        delay_seconds = 1
    else:
        delay_seconds = 0
    return datetime.now(UTC) + timedelta(seconds=delay_seconds)


def _transient_failure(response: GatewayToolResponse) -> bool:
    if response.ok:
        return False
    code = response.error.get("code") if response.error else None
    return code in {
        "timeout",
        "network_failure",
        "tool_server_unavailable",
        "server_500",
        "rate_limit_exceeded",
    }


def _response_error(response: GatewayToolResponse) -> str:
    if response.error:
        return (
            response.error.get("message")
            or response.error.get("code")
            or "tool execution failed"
        )
    if not isinstance(response.data, dict):
        return "malformed tool output"
    return "tool execution failed"


def _audit_event(
    event_type: str,
    actor: str,
    role: str,
    message: str,
    node_id: str | None = None,
) -> WorkflowAuditEvent:
    return WorkflowAuditEvent(
        event_type=event_type,
        actor=actor,
        role=role,
        message=message,
        node_id=node_id,
    )


def _augment_tools_from_knowledge(
    discovered_tools: list[ToolDocument],
    all_tools: list[ToolDocument],
    knowledge_response: EngineeringKnowledgeSearchResponse,
    *,
    role: str,
) -> list[ToolDocument]:
    existing = {tool.name for tool in discovered_tools}
    evidence_text = " ".join(
        " ".join([result.chunk.metadata.title, result.chunk.text])
        for result in knowledge_response.results
    ).lower()
    additions: list[ToolDocument] = []
    for tool in all_tools:
        if tool.name in existing:
            continue
        if tool.name.lower() not in evidence_text:
            continue
        if not tool.enabled:
            continue
        allowed_roles = {item.upper() for item in tool.required_roles}
        if tool.required_roles and role.upper() not in allowed_roles:
            continue
        additions.append(tool)
        existing.add(tool.name)
    return [*discovered_tools, *additions]


def _filter_planner_visible_tools(
    tools: list[ToolDocument],
    *,
    evaluator: WorkflowPolicyEvaluator,
    request: WorkflowPlanRequest,
) -> list[ToolDocument]:
    filtered: list[ToolDocument] = []
    for tool in tools:
        node = WorkflowNode(
            id=f"policy_check_{tool.name}"[:120],
            tool_name=tool.name,
            tool_server=tool.server,
            description=tool.description,
            arguments=_planning_filter_arguments(tool, request),
            risk_level=tool.risk_level,
            approval_required=tool.risk_level in {"HIGH", "CRITICAL"},
        )
        evaluation = evaluator.evaluate(
            node,
            actor=request.created_by,
            role=request.role,
            environment=request.target_environment,
            phase="planning",
        )
        if evaluation.decision in {PolicyDecision.ALLOW, PolicyDecision.ALLOW_WITH_APPROVAL}:
            filtered.append(tool)
    return filtered


def _planning_filter_arguments(tool: ToolDocument, request: WorkflowPlanRequest) -> dict[str, Any]:
    properties = tool.input_schema.get("properties", {})
    if not isinstance(properties, dict):
        return {}
    arguments: dict[str, Any] = {}
    configured_repository = _configured_repository()
    if "repository" in properties and configured_repository:
        arguments["repository"] = configured_repository
    device = _device_from_request(request.user_request)
    if "device_id" in properties and device:
        arguments["device_id"] = device
    if "environment" in properties:
        arguments["environment"] = request.target_environment
    return arguments


def _configured_repository() -> str | None:
    from mcp_ops_common.config import get_settings

    settings = get_settings()
    if settings.github_owner and settings.github_repo:
        return f"{settings.github_owner}/{settings.github_repo}"
    allowed = [
        item.strip()
        for item in settings.github_allowed_repositories.split(",")
        if item.strip()
    ]
    return sorted(allowed)[0] if allowed else None


def _device_from_request(user_request: str) -> str | None:
    import re

    match = re.search(r"\bSIM-\d{3}\b", user_request, flags=re.IGNORECASE)
    return match.group(0).upper() if match else None


def _role_token(role: str) -> str:
    return {
        "VIEWER": "viewer-token",
        "ENGINEER": "engineer-token",
        "OPERATOR": "operator-token",
        "ADMIN": "admin-token",
    }.get(role.upper(), "viewer-token")


def _denied_response(node: WorkflowNode, code: str) -> GatewayToolResponse:
    from uuid import uuid4

    return GatewayToolResponse(
        ok=False,
        decision=GatewayDecision.DENIED,
        correlation_id=uuid4(),
        data={"tool_name": node.tool_name},
        error={"code": code, "message": f"{node.tool_name} is not executable through the gateway."},
    )


def _failure_response(node: WorkflowNode, code: str, message: str) -> GatewayToolResponse:
    from uuid import uuid4

    return GatewayToolResponse(
        ok=False,
        decision=GatewayDecision.DENIED,
        correlation_id=uuid4(),
        data={"tool_name": node.tool_name},
        error={"code": code, "message": message or f"{node.tool_name} failed."},
    )
