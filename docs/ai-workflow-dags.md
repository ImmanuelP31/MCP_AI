# AI-Generated Engineering Workflow DAGs

This feature turns a natural-language engineering request into a validated, policy-transformed
workflow DAG before any execution happens. The planner does not receive the full MCP catalog. It only
receives tools returned by semantic tool discovery after role and policy filtering.

Trust boundary: **AI recommends. Policy authorizes. Human approves. MCP executes. Audit records.**

```mermaid
flowchart TD
    A["Natural-language engineering request"] --> B["Semantic MCP tool discovery"]
    B --> C["Policy and RBAC pre-filter"]
    C --> D["Typed workflow planner"]
    D --> E["Pydantic schema validation"]
    E --> F["Tool existence and argument validation"]
    F --> G["DAG validation"]
    G --> H["Policy evaluation"]
    H --> I["Policy-transformed workflow"]
    I --> J["Persisted workflow plus audit events"]
    J --> K["Explicit execute request"]
    K --> L["Fresh policy re-check"]
    L --> M["Human approval where required"]
    M --> N["MCP gateway only"]
```

## Example

Request:

```json
{
  "user_request": "Check why the latest build failed and create a ticket if the problem comes from our code.",
  "role": "ENGINEER",
  "created_by": "engineer",
  "top_k": 10
}
```

Possible validated workflow:

```mermaid
flowchart TD
    A["get_build_status"] --> B["get_pipeline_logs"]
    B --> C["get_recent_commits"]
    C --> D["analyze_build_failure"]
    D -->|source_code_failure| E["create_ticket"]
```

The exact nodes depend on the policy-filtered tools retrieved for the request.

## Planner Modes

Default test/local mode:

```env
LLM_PLANNER_PROVIDER=deterministic
```

Live demo mode:

```env
GEMINI_API_KEY=your-valid-gemini-key
GEMINI_MODEL=gemini-3.5-flash
LLM_PLANNER_PROVIDER=gemini
```

OpenRouter remains supported for planner comparison by setting `OPENROUTER_API_KEY` and
`LLM_PLANNER_PROVIDER=openrouter`.

`LLMWorkflowPlanner` asks live providers for a compact `PlannerDecision`, not the final trusted
workflow object. The model can only return:

- `decision`: `PLAN`, `CLARIFY`, or `REFUSE`
- `confidence`
- `reason`
- `missing_context`
- node proposals containing `id`, `tool_name`, `arguments`, `depends_on`, typed `condition`, and
  optional `knowledge_references`

The model does not generate `tool_server`, `description`, `risk_level`, `approval_required`,
`planner_model`, retry policy, timeout, compensation, or workflow identifiers. It also does not
generate edges; the backend derives edges from `depends_on`.

For Gemini, the request includes a JSON response schema for `PlannerDecision` in addition to JSON
MIME mode. The resulting proposal is compiled by trusted backend code into `WorkflowPlanDraft` using
the MCP tool registry. That draft is still untrusted. The backend validator then checks tool
existence, discovered-tool membership, arguments, DAG structure, size limits, RBAC, risk, and
approval policy.

`CLARIFY` and `REFUSE` are valid no-action planner decisions. They are persisted as zero-node
workflow records with the reason and missing context in `original_plan`, instead of being counted as
malformed planner output.

Live planner configuration fails closed in production and real-evaluation mode. If
`LLM_PLANNER_PROVIDER=gemini` is requested without a valid `GEMINI_API_KEY`, planning raises a
configuration error instead of silently switching to the deterministic planner. Deterministic
fallback is reserved for explicitly configured development/test paths.

## Argument Binding

The LLM may propose concrete arguments, but trusted registry metadata still controls tool identity,
server, risk, and approval requirements. Proposed arguments are accepted only when they match the
tool input schema and resource allowlist checks.

For values that should come from earlier workflow steps, the planner can emit typed references:

```json
{
  "id": "logs",
  "tool_name": "get_pipeline_logs",
  "depends_on": ["failed_jobs"],
  "arguments": {
    "repository": "ImmanuelP31/MCP_AI",
    "job_id": { "$from": "failed_jobs.jobs.0.id" }
  }
}
```

The backend stores this as an `argument_references` record, validates that the source is an actual
dependency, and resolves it immediately before execution. The resolved arguments are checkpointed
before gateway routing, approval binding, idempotency hashing, and audit logging.

Policy can transform a proposed plan:

```mermaid
flowchart TD
    A["get_pipeline_logs: ALLOW"] --> B["rollback_production: ALLOW_WITH_APPROVAL"]
    B --> C["delete_bad_deployment: DENY"]
```

Supported policy outcomes:

- `ALLOW`
- `ALLOW_WITH_APPROVAL`
- `DENY`
- `REQUIRE_ADDITIONAL_CONTEXT`

Every workflow node includes a policy evaluation record with actor, role, tool, target resource,
environment, trusted risk, policy decision, matched rule, reason, and timestamp.

## API

Plan without executing:

```http
POST /api/v1/workflows/plan
Content-Type: application/json

{
  "user_request": "Create a maintenance ticket for SIM-014.",
  "role": "ENGINEER",
  "created_by": "engineer",
  "target_environment": "production",
  "top_k": 20
}
```

Read workflow state:

```http
GET /api/v1/workflows/{workflow_id}
```

Execute an existing workflow:

```http
POST /api/v1/workflows/{workflow_id}/execute
Content-Type: application/json

{
  "role": "OPERATOR"
}
```

Cancel:

```http
POST /api/v1/workflows/{workflow_id}/cancel
```

## Security Guarantees

- Tool discovery happens before planning, so the planner only sees relevant authorized tools.
- Planner output is a strict Pydantic model, not free-form text.
- Live LLM output is schema-normalized only to tolerate JSON shape differences; trusted risk,
  approval, retry, timeout, executable status, and server metadata still come from the backend
  registry.
- Validation rejects unknown tools, undiscovered tools, disabled tools, invalid arguments, cycles,
  missing dependencies, and oversized workflows.
- Policy evaluation determines `ALLOW`, `ALLOW_WITH_APPROVAL`, `DENY`, or
  `REQUIRE_ADDITIONAL_CONTEXT`.
- Environment-aware policy supports different decisions for `dev`, `staging`, and `production`.
- The model cannot set trusted authorization fields such as `authorized=true`, `approval=false`, or
  `risk_level=LOW`; risk and approval requirements are derived from backend policy metadata.
- High-risk and critical tools are marked approval-required only by trusted policy.
- Planning and execution are separate operations.
- Policy is re-evaluated immediately before execution to prevent stale decisions.
- Execution goes through the MCP gateway. The workflow service does not directly call databases,
  Kafka, Redis, OpenSearch, shell commands, or simulator internals.
- Model-supplied approval tokens and authorization fields remain untrusted by the gateway.

## Persistence

Workflows are represented by these PostgreSQL tables:

- `workflows`
- `workflow_nodes`
- `workflow_edges`

Workflow records also store the original AI plan, policy-transformed plan, node policy evaluations,
and workflow audit events.

The Alembic migration is:

- `apps/api/alembic/versions/2026_08_11_0003_workflow_dag.py`

## Metrics

- `ai_workflows_planned_total`
- `ai_workflow_plan_failures_total`
- `ai_workflow_nodes_total`
- `ai_workflow_planning_latency_seconds`
- `ai_workflow_validation_failures_total`
- `policy_evaluations_total`
- `policy_denials_total`
- `policy_approval_required_total`
- `policy_bypass_attempts_total`
