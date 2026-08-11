# Resilient Agentic Workflow Execution

The workflow executor supports recovery from partial failure without replanning or restarting completed workflow nodes.

## Execution State Model

Workflow nodes persist these execution states:

- `PENDING`
- `READY`
- `RUNNING`
- `SUCCEEDED`
- `FAILED`
- `RETRYING`
- `WAITING_APPROVAL`
- `COMPENSATING`
- `COMPENSATED`
- `BLOCKED`
- `CANCELLED`

The project also keeps `DENIED` and `SKIPPED` for backward compatibility with existing policy and conditional workflow behavior.

## Durable Node Checkpoints

Each workflow node persists:

- attempts
- max retries
- retry strategy
- timeout
- last error
- started/completed/attempt timestamps
- next retry timestamp
- tool result reference
- compensation tool

Checkpoints are written after every meaningful node transition: ready, started, succeeded, failed, retrying, waiting for approval, compensation started, compensation completed, and workflow completed.

## Retry Policy

Supported retry policies:

- `NO_RETRY`
- `FIXED_DELAY`
- `EXPONENTIAL_BACKOFF`

Retry policy comes from trusted MCP tool metadata, not from LLM output.

Non-idempotent tools are retried only when one of these is true:

- tool metadata marks the tool retry-safe
- an idempotency key exists
- the tool itself is idempotent

Workflow execution always sends a deterministic idempotency key to the MCP gateway:

```text
workflow-{workflow_id}-{node_id}
```

## Compensation

Compensation is explicit. The executor does not assume every action is reversible.

Current compensation declarations:

- `deploy_staging` -> `restore_previous_staging_release`
- `create_ticket` -> `close_ticket_if_created_by_failed_workflow`

Compensation runs only when the failed node declares a compensation tool.

## API

Execute a planned workflow:

```http
POST /api/v1/workflows/{id}/execute
```

Resume from a persisted checkpoint:

```http
POST /api/v1/workflows/{id}/resume
```

Retry a single node:

```http
POST /api/v1/workflows/{id}/retry/{node_id}
```

Planning and execution remain separate. Resume and retry do not call the planner again.

## Workflow Events

The executor publishes workflow lifecycle events through `WorkflowEventPublisher`.

Supported event names include:

- `workflow.started`
- `workflow.node.started`
- `workflow.node.succeeded`
- `workflow.node.failed`
- `workflow.node.retrying`
- `workflow.approval.required`
- `workflow.compensation.started`
- `workflow.completed`

The default test/runtime implementation is in-memory. A Kafka adapter can plug into this interface without changing the executor. If event publishing is temporarily unavailable, the executor records an audit event and keeps the workflow checkpoint.

## Metrics

Prometheus metrics:

- `workflow_executions_total`
- `workflow_execution_failures_total`
- `workflow_retries_total`
- `workflow_compensations_total`
- `workflow_recovery_success_total`
- `workflow_execution_duration_seconds`

## Frontend

The workflow page includes an execution timeline showing node status, attempts, retry strategy, timeout, result reference, timestamps, last error, and compensation tool. Failed nodes expose a retry control. Workflows expose a resume control.

## Trust Boundary

AI proposes workflows. Policy authorizes. Human approvals gate high-risk actions. MCP executes. The workflow engine checkpoints and recovers from failures without trusting LLM-supplied retry, risk, approval, or compensation claims.
