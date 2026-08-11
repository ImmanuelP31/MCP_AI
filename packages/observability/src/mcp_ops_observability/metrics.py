from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

REGISTRY = CollectorRegistry(auto_describe=True)

API_LATENCY_SECONDS = Histogram(
    "mcp_ops_api_latency_seconds",
    "API request latency in seconds.",
    ["method", "path", "status_code"],
    registry=REGISTRY,
)
API_REQUESTS_TOTAL = Counter(
    "mcp_ops_api_requests_total",
    "Total API requests.",
    ["method", "path", "status_code"],
    registry=REGISTRY,
)
API_ERRORS_TOTAL = Counter(
    "mcp_ops_api_errors_total",
    "Total API error responses.",
    ["method", "path", "status_code"],
    registry=REGISTRY,
)
MCP_CALLS_TOTAL = Counter(
    "mcp_ops_mcp_calls_total",
    "Total governed MCP calls.",
    ["tool_name", "domain", "decision"],
    registry=REGISTRY,
)
MCP_FAILURES_TOTAL = Counter(
    "mcp_ops_mcp_failures_total",
    "Total MCP tool failures.",
    ["tool_name", "domain", "error_code"],
    registry=REGISTRY,
)
TOOL_LATENCY_SECONDS = Histogram(
    "mcp_ops_tool_latency_seconds",
    "Governed MCP tool latency in seconds.",
    ["tool_name", "domain", "decision"],
    registry=REGISTRY,
)
TOOL_AUTHORIZATION_FAILURES_TOTAL = Counter(
    "mcp_ops_tool_authorization_failures_total",
    "Tool authorization failures.",
    ["tool_name", "required_permission", "role"],
    registry=REGISTRY,
)
APPROVAL_LATENCY_SECONDS = Histogram(
    "mcp_ops_approval_latency_seconds",
    "Approval workflow latency in seconds.",
    ["tool_name", "risk_level", "status"],
    registry=REGISTRY,
)
DEVICE_HEALTH_SCORE = Gauge(
    "mcp_ops_device_health_score",
    "Current simulator device health score.",
    ["device_id", "status"],
    registry=REGISTRY,
)
KAFKA_CONSUMER_LAG = Gauge(
    "mcp_ops_kafka_consumer_lag",
    "Kafka consumer lag by topic and consumer group.",
    ["topic", "consumer_group"],
    registry=REGISTRY,
)
DATABASE_LATENCY_SECONDS = Histogram(
    "mcp_ops_database_latency_seconds",
    "Database operation latency in seconds.",
    ["operation"],
    registry=REGISTRY,
)
REDIS_LATENCY_SECONDS = Histogram(
    "mcp_ops_redis_latency_seconds",
    "Redis operation latency in seconds.",
    ["operation"],
    registry=REGISTRY,
)
OPENSEARCH_LATENCY_SECONDS = Histogram(
    "mcp_ops_opensearch_latency_seconds",
    "OpenSearch operation latency in seconds.",
    ["operation"],
    registry=REGISTRY,
)
AGENT_DECISIONS_TOTAL = Counter(
    "mcp_ops_agent_decisions_total",
    "AI agent decisions by intent, outcome, and escalation status.",
    ["intent", "outcome", "escalation_required"],
    registry=REGISTRY,
)
AGENT_TOOL_FAILURES_TOTAL = Counter(
    "mcp_ops_agent_tool_failures_total",
    "AI agent governed tool workflow failures.",
    ["intent", "tool_name", "error_code"],
    registry=REGISTRY,
)
MCP_TOOL_DISCOVERY_REQUESTS_TOTAL = Counter(
    "mcp_tool_discovery_requests_total",
    "Total semantic MCP tool discovery requests.",
    ["role", "index_backend"],
    registry=REGISTRY,
)
MCP_TOOL_DISCOVERY_LATENCY_SECONDS = Histogram(
    "mcp_tool_discovery_latency_seconds",
    "Semantic MCP tool discovery latency in seconds.",
    ["role", "index_backend"],
    registry=REGISTRY,
)
MCP_TOOL_DISCOVERY_RESULTS_TOTAL = Counter(
    "mcp_tool_discovery_results_total",
    "Total semantic MCP tool discovery results returned.",
    ["role", "index_backend"],
    registry=REGISTRY,
)
MCP_TOOL_DISCOVERY_EMPTY_RESULTS_TOTAL = Counter(
    "mcp_tool_discovery_empty_results_total",
    "Total semantic MCP tool discovery requests with no returned tools.",
    ["role", "index_backend"],
    registry=REGISTRY,
)
AI_WORKFLOWS_PLANNED_TOTAL = Counter(
    "ai_workflows_planned_total",
    "Total AI-generated engineering workflows successfully planned.",
    ["role", "planner_model"],
    registry=REGISTRY,
)
AI_WORKFLOW_PLAN_FAILURES_TOTAL = Counter(
    "ai_workflow_plan_failures_total",
    "Total AI workflow planning failures.",
    ["role", "reason"],
    registry=REGISTRY,
)
AI_WORKFLOW_NODES_TOTAL = Counter(
    "ai_workflow_nodes_total",
    "Total AI workflow nodes planned.",
    ["role", "planner_model"],
    registry=REGISTRY,
)
AI_WORKFLOW_PLANNING_LATENCY_SECONDS = Histogram(
    "ai_workflow_planning_latency_seconds",
    "AI workflow planning latency in seconds.",
    ["role", "planner_model", "outcome"],
    registry=REGISTRY,
)
AI_WORKFLOW_VALIDATION_FAILURES_TOTAL = Counter(
    "ai_workflow_validation_failures_total",
    "Total AI workflow validation failures by code.",
    ["role", "code"],
    registry=REGISTRY,
)
POLICY_EVALUATIONS_TOTAL = Counter(
    "policy_evaluations_total",
    "Total workflow policy evaluations.",
    ["role", "tool_name", "environment", "decision"],
    registry=REGISTRY,
)
POLICY_DENIALS_TOTAL = Counter(
    "policy_denials_total",
    "Total workflow policy denials.",
    ["role", "tool_name", "environment"],
    registry=REGISTRY,
)
POLICY_APPROVAL_REQUIRED_TOTAL = Counter(
    "policy_approval_required_total",
    "Total workflow policy decisions requiring approval.",
    ["role", "tool_name", "environment"],
    registry=REGISTRY,
)
POLICY_BYPASS_ATTEMPTS_TOTAL = Counter(
    "policy_bypass_attempts_total",
    "Total LLM policy bypass attempts detected during workflow planning.",
    ["role", "tool_name", "environment", "field"],
    registry=REGISTRY,
)
WORKFLOW_EXECUTIONS_TOTAL = Counter(
    "workflow_executions_total",
    "Total workflow execution attempts.",
    ["role", "outcome"],
    registry=REGISTRY,
)
WORKFLOW_EXECUTION_FAILURES_TOTAL = Counter(
    "workflow_execution_failures_total",
    "Total workflow execution failures.",
    ["role", "reason"],
    registry=REGISTRY,
)
WORKFLOW_RETRIES_TOTAL = Counter(
    "workflow_retries_total",
    "Total workflow node retries.",
    ["role", "tool_name", "strategy"],
    registry=REGISTRY,
)
WORKFLOW_COMPENSATIONS_TOTAL = Counter(
    "workflow_compensations_total",
    "Total workflow compensating actions.",
    ["role", "tool_name", "outcome"],
    registry=REGISTRY,
)
WORKFLOW_RECOVERY_SUCCESS_TOTAL = Counter(
    "workflow_recovery_success_total",
    "Total workflow recovery attempts that resumed successfully.",
    ["role"],
    registry=REGISTRY,
)
WORKFLOW_EXECUTION_DURATION_SECONDS = Histogram(
    "workflow_execution_duration_seconds",
    "Workflow execution duration in seconds.",
    ["role", "outcome"],
    registry=REGISTRY,
)
MCP_SECURITY_EVENTS_TOTAL = Counter(
    "mcp_security_events_total",
    "Total MCP control-plane security events.",
    ["event_type", "severity"],
    registry=REGISTRY,
)
MCP_TOOL_METADATA_REJECTIONS_TOTAL = Counter(
    "mcp_tool_metadata_rejections_total",
    "Total rejected MCP tool metadata registrations.",
    ["reason"],
    registry=REGISTRY,
)
MCP_HALLUCINATED_TOOL_CALLS_TOTAL = Counter(
    "mcp_hallucinated_tool_calls_total",
    "Total planner outputs referencing nonexistent or undiscovered MCP tools.",
    ["planner_model", "tool_name"],
    registry=REGISTRY,
)
MCP_ARGUMENT_VALIDATION_FAILURES_TOTAL = Counter(
    "mcp_argument_validation_failures_total",
    "Total MCP argument validation failures.",
    ["tool_name", "reason"],
    registry=REGISTRY,
)
MCP_PROMPT_INJECTION_DETECTIONS_TOTAL = Counter(
    "mcp_prompt_injection_detections_total",
    "Total prompt-injection-like content detections.",
    ["source"],
    registry=REGISTRY,
)
MCP_APPROVAL_REPLAY_ATTEMPTS_TOTAL = Counter(
    "mcp_approval_replay_attempts_total",
    "Total approval replay or approval-binding mismatch attempts.",
    ["tool_name", "reason"],
    registry=REGISTRY,
)
RAG_QUERIES_TOTAL = Counter(
    "rag_queries_total",
    "Total engineering knowledge RAG queries.",
    ["mode", "index_backend"],
    registry=REGISTRY,
)
RAG_QUERY_LATENCY_SECONDS = Histogram(
    "rag_query_latency_seconds",
    "Engineering knowledge RAG query latency in seconds.",
    ["mode", "index_backend"],
    registry=REGISTRY,
)
RAG_EMPTY_RESULTS_TOTAL = Counter(
    "rag_empty_results_total",
    "Engineering knowledge RAG queries with no retrieved documents.",
    ["mode", "index_backend"],
    registry=REGISTRY,
)
RAG_DOCUMENTS_RETRIEVED_TOTAL = Counter(
    "rag_documents_retrieved_total",
    "Total engineering knowledge documents retrieved by RAG.",
    ["mode", "index_backend"],
    registry=REGISTRY,
)
AI_WORKFLOW_EVALUATION_RUNS_TOTAL = Counter(
    "ai_workflow_evaluation_runs_total",
    "Total AI engineering workflow benchmark summaries recorded.",
    ["config", "mode"],
    registry=REGISTRY,
)
AI_WORKFLOW_EVALUATION_SCORE = Gauge(
    "ai_workflow_evaluation_score",
    "Latest AI engineering workflow benchmark metric score.",
    ["config", "mode", "metric"],
    registry=REGISTRY,
)


def metrics_response() -> bytes:
    return generate_latest(REGISTRY)


def record_api_request(method: str, path: str, status_code: int, latency_seconds: float) -> None:
    labels = (method, path, str(status_code))
    API_REQUESTS_TOTAL.labels(*labels).inc()
    API_LATENCY_SECONDS.labels(*labels).observe(latency_seconds)
    if status_code >= 500:
        API_ERRORS_TOTAL.labels(*labels).inc()


def record_mcp_call(
    *,
    tool_name: str,
    domain: str,
    decision: str,
    latency_seconds: float,
) -> None:
    MCP_CALLS_TOTAL.labels(tool_name, domain, decision).inc()
    TOOL_LATENCY_SECONDS.labels(tool_name, domain, decision).observe(latency_seconds)


def record_mcp_failure(tool_name: str, domain: str, error_code: str) -> None:
    MCP_FAILURES_TOTAL.labels(tool_name, domain, error_code).inc()


def record_authorization_failure(
    *,
    tool_name: str,
    required_permission: str,
    role: str,
) -> None:
    TOOL_AUTHORIZATION_FAILURES_TOTAL.labels(tool_name, required_permission, role).inc()


def observe_approval_latency(
    *,
    tool_name: str,
    risk_level: str,
    status: str,
    latency_seconds: float,
) -> None:
    APPROVAL_LATENCY_SECONDS.labels(tool_name, risk_level, status).observe(latency_seconds)


def set_device_health(device_id: str, status: str, health_score: float) -> None:
    DEVICE_HEALTH_SCORE.labels(device_id, status).set(health_score)


def set_kafka_consumer_lag(topic: str, consumer_group: str, lag: int) -> None:
    KAFKA_CONSUMER_LAG.labels(topic, consumer_group).set(lag)


def observe_database_latency(operation: str, latency_seconds: float) -> None:
    DATABASE_LATENCY_SECONDS.labels(operation).observe(latency_seconds)


def observe_redis_latency(operation: str, latency_seconds: float) -> None:
    REDIS_LATENCY_SECONDS.labels(operation).observe(latency_seconds)


def observe_opensearch_latency(operation: str, latency_seconds: float) -> None:
    OPENSEARCH_LATENCY_SECONDS.labels(operation).observe(latency_seconds)


def record_agent_decision(
    *,
    intent: str,
    outcome: str,
    escalation_required: bool,
) -> None:
    AGENT_DECISIONS_TOTAL.labels(intent, outcome, str(escalation_required).lower()).inc()


def record_agent_tool_failure(
    *,
    intent: str,
    tool_name: str,
    error_code: str,
) -> None:
    AGENT_TOOL_FAILURES_TOTAL.labels(intent, tool_name, error_code).inc()


def record_tool_discovery_request(
    *,
    role: str,
    index_backend: str,
    result_count: int,
    latency_seconds: float,
) -> None:
    MCP_TOOL_DISCOVERY_REQUESTS_TOTAL.labels(role, index_backend).inc()
    MCP_TOOL_DISCOVERY_LATENCY_SECONDS.labels(role, index_backend).observe(latency_seconds)
    MCP_TOOL_DISCOVERY_RESULTS_TOTAL.labels(role, index_backend).inc(result_count)
    if result_count == 0:
        MCP_TOOL_DISCOVERY_EMPTY_RESULTS_TOTAL.labels(role, index_backend).inc()


def record_workflow_planned(
    *,
    role: str,
    planner_model: str,
    node_count: int,
    latency_seconds: float,
) -> None:
    AI_WORKFLOWS_PLANNED_TOTAL.labels(role, planner_model).inc()
    AI_WORKFLOW_NODES_TOTAL.labels(role, planner_model).inc(node_count)
    AI_WORKFLOW_PLANNING_LATENCY_SECONDS.labels(role, planner_model, "ok").observe(
        latency_seconds
    )


def record_workflow_plan_failure(
    *,
    role: str,
    planner_model: str,
    reason: str,
    latency_seconds: float,
) -> None:
    AI_WORKFLOW_PLAN_FAILURES_TOTAL.labels(role, reason).inc()
    AI_WORKFLOW_PLANNING_LATENCY_SECONDS.labels(role, planner_model, "failed").observe(
        latency_seconds
    )


def record_workflow_validation_failure(*, role: str, code: str) -> None:
    AI_WORKFLOW_VALIDATION_FAILURES_TOTAL.labels(role, code).inc()


def record_policy_evaluation(
    *,
    role: str,
    tool_name: str,
    environment: str,
    decision: str,
) -> None:
    POLICY_EVALUATIONS_TOTAL.labels(role, tool_name, environment, decision).inc()


def record_policy_denial(*, role: str, tool_name: str, environment: str) -> None:
    POLICY_DENIALS_TOTAL.labels(role, tool_name, environment).inc()


def record_policy_approval_required(*, role: str, tool_name: str, environment: str) -> None:
    POLICY_APPROVAL_REQUIRED_TOTAL.labels(role, tool_name, environment).inc()


def record_policy_bypass_attempt(
    *,
    role: str,
    tool_name: str,
    environment: str,
    field: str,
) -> None:
    POLICY_BYPASS_ATTEMPTS_TOTAL.labels(role, tool_name, environment, field).inc()


def record_workflow_execution(
    *,
    role: str,
    outcome: str,
    duration_seconds: float,
) -> None:
    WORKFLOW_EXECUTIONS_TOTAL.labels(role, outcome).inc()
    WORKFLOW_EXECUTION_DURATION_SECONDS.labels(role, outcome).observe(duration_seconds)


def record_workflow_execution_failure(*, role: str, reason: str) -> None:
    WORKFLOW_EXECUTION_FAILURES_TOTAL.labels(role, reason).inc()


def record_workflow_retry(*, role: str, tool_name: str, strategy: str) -> None:
    WORKFLOW_RETRIES_TOTAL.labels(role, tool_name, strategy).inc()


def record_workflow_compensation(*, role: str, tool_name: str, outcome: str) -> None:
    WORKFLOW_COMPENSATIONS_TOTAL.labels(role, tool_name, outcome).inc()


def record_workflow_recovery_success(*, role: str) -> None:
    WORKFLOW_RECOVERY_SUCCESS_TOTAL.labels(role).inc()


def record_mcp_security_event(*, event_type: str, severity: str) -> None:
    MCP_SECURITY_EVENTS_TOTAL.labels(event_type, severity).inc()


def record_tool_metadata_rejection(*, reason: str) -> None:
    MCP_TOOL_METADATA_REJECTIONS_TOTAL.labels(reason).inc()
    record_mcp_security_event(event_type="tool_metadata_rejected", severity="HIGH")


def record_hallucinated_tool_call(*, planner_model: str, tool_name: str) -> None:
    MCP_HALLUCINATED_TOOL_CALLS_TOTAL.labels(planner_model, tool_name).inc()
    record_mcp_security_event(event_type="hallucinated_tool", severity="MEDIUM")


def record_argument_validation_failure(*, tool_name: str, reason: str) -> None:
    MCP_ARGUMENT_VALIDATION_FAILURES_TOTAL.labels(tool_name, reason).inc()
    record_mcp_security_event(event_type="argument_validation_failed", severity="MEDIUM")


def record_prompt_injection_detection(*, source: str) -> None:
    MCP_PROMPT_INJECTION_DETECTIONS_TOTAL.labels(source).inc()
    record_mcp_security_event(event_type="prompt_injection_detected", severity="HIGH")


def record_approval_replay_attempt(*, tool_name: str, reason: str) -> None:
    MCP_APPROVAL_REPLAY_ATTEMPTS_TOTAL.labels(tool_name, reason).inc()
    record_mcp_security_event(event_type="approval_replay_attempt", severity="HIGH")


def record_rag_query(
    *,
    mode: str,
    index_backend: str,
    result_count: int,
    latency_seconds: float,
) -> None:
    RAG_QUERIES_TOTAL.labels(mode, index_backend).inc()
    RAG_QUERY_LATENCY_SECONDS.labels(mode, index_backend).observe(latency_seconds)
    RAG_DOCUMENTS_RETRIEVED_TOTAL.labels(mode, index_backend).inc(result_count)
    if result_count == 0:
        RAG_EMPTY_RESULTS_TOTAL.labels(mode, index_backend).inc()


def record_ai_evaluation_summary(
    *,
    config: str,
    mode: str,
    metrics: dict[str, object],
) -> None:
    AI_WORKFLOW_EVALUATION_RUNS_TOTAL.labels(config, mode).inc()
    for key, value in metrics.items():
        if key in {"config", "mode"} or not isinstance(value, int | float):
            continue
        AI_WORKFLOW_EVALUATION_SCORE.labels(config, mode, key).set(float(value))
