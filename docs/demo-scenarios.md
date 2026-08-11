# Phase 13 Demo Scenarios

This demo is deterministic and uses the fixed simulator timestamp
`2026-01-15T12:00:00+00:00`. It is intended for engineering walkthroughs where the
audience needs to see fleet monitoring, incident investigation, MCP governance,
knowledge lookup, ticket creation, high-risk approval, execution, and audit evidence.

The Python demo commands run against in-memory deterministic services. They do not require
PostgreSQL, Redis, Kafka, or OpenSearch to be running. The dashboard command serves the built
React frontend so the presenter can open the UI alongside the transcript.

## Prerequisites

From the repository root:

```powershell
$py = "C:\Users\Imman\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
```

## Reset The Demo Environment

Command:

```powershell
& $py scripts\demo\reset_demo_environment.py
```

Expected output:

```json
{
  "demo_environment": "reset",
  "device_count": 50,
  "distribution": {
    "CRITICAL": 0,
    "HEALTHY": 50,
    "OFFLINE": 0,
    "WARNING": 0
  },
  "sim_014": {
    "active_scenario": null,
    "health_score": 96.0,
    "status": "HEALTHY"
  },
  "timestamp": "2026-01-15T12:00:00+00:00"
}
```

The service map for `SIM-014` should show `control-plane`, `diagnostic-runner`,
`sensor-ingestor`, and `telemetry-agent` all in `RUNNING`.

## Open The Dashboard

Commands:

```powershell
cd apps\frontend
npm run build
npm run preview:e2e
```

Then open:

```powershell
Start-Process http://127.0.0.1:4173/dashboard
```

Expected dashboard talking points:

| Item | Expected Value |
| --- | --- |
| Fleet size | 50 devices |
| Baseline health | 50 healthy, 0 warning, 0 critical, 0 offline |
| Device detail to inspect | `SIM-014` |
| Baseline telemetry sample | CPU `67.0`, memory `35.0`, latency `123.0ms`, packet loss `0.4%` |
| Active generated incidents before trigger | 0 |

Stop the preview server with `Ctrl+C` when the UI portion is done.

## Run The Complete Deterministic Transcript

Command:

```powershell
cd ..\..
& $py scripts\demo\run_phase13_demo.py
```

The command prints one JSON document with five `demos`.

## DEMO 1 - Fleet Monitoring

Expected fields:

```json
{
  "name": "DEMO 1 - Fleet monitoring",
  "dashboard_route": "/dashboard",
  "device_count": 50,
  "distribution": {
    "CRITICAL": 0,
    "HEALTHY": 50,
    "OFFLINE": 0,
    "WARNING": 0
  },
  "active_incidents": 0
}
```

Expected telemetry sample for `SIM-014`:

```json
{
  "cpu_percent": 67.0,
  "memory_percent": 35.0,
  "network_latency_ms": 123.0,
  "packet_loss_percent": 0.4,
  "disk_percent": 59.0
}
```

## DEMO 2 - Incident Investigation

Trigger shown in the transcript:

```text
POST /simulator/scenarios/SIM-014/network-timeout
```

Expected alert:

```json
{
  "device_id": "SIM-014",
  "error_code": "E-NET-TIMEOUT",
  "severity": "CRITICAL",
  "message": "Network timeout threshold exceeded."
}
```

Expected incident:

```json
{
  "device_id": "SIM-014",
  "incident_id": "5cdf2262-e194-5b16-865e-c29a3eb603a9",
  "status": "OPEN",
  "title": "SIM-014 threshold breach: E-NET-TIMEOUT"
}
```

Expected health degradation:

```json
{
  "device_id": "SIM-014",
  "health_score": 18.0,
  "status": "CRITICAL"
}
```

Expected telemetry evidence:

```json
{
  "network_latency_ms": 5000.0,
  "packet_loss_percent": 100.0,
  "service_states": {
    "telemetry-agent": "DEGRADED"
  }
}
```

Expected governed tool sequence:

| Step | Tool | Decision |
| --- | --- | --- |
| 1 | `get_device_health` | `ALLOWED` |
| 2 | `search_logs` | `ALLOWED` |
| 3 | `get_device_telemetry` | `ALLOWED` |
| 4 | `get_device_status` | `ALLOWED` |
| 5 | `get_device_services` | `ALLOWED` |
| 6 | `get_recent_errors` | `ALLOWED` |
| 7 | `find_similar_incidents` | `ALLOWED` |
| 8 | `run_diagnostic_check` | `ALLOWED` |
| 9 | `generate_diagnostic_summary` | `ALLOWED` |

Expected diagnostic conclusion:

```text
SIM-014 is CRITICAL. Deterministic diagnostics indicate network communication issue,
sensor initialization failure.
```

Expected historical similar incident:

```json
{
  "incident_id": "INC-NET-001",
  "title": "Packet loss with network timeout errors",
  "signals": ["packet_loss", "network_timeout_error", "degraded_service"]
}
```

## DEMO 3 - Knowledge-Assisted Diagnosis

Prompt:

```text
What procedure should I follow for this failure?
```

Expected MCP tools:

| Step | Tool | Expected Source |
| --- | --- | --- |
| 1 | `search_knowledge` | Network timeout procedure query |
| 2 | `get_procedure` | `kb-service-restart` |
| 3 | `find_troubleshooting_steps` | `E-NET-TIMEOUT` |

Expected source document:

```json
{
  "document_id": "kb-service-restart",
  "procedure": "Service Restart Procedure",
  "source_citation": "kb-service-restart@1.0-demo#restart-governance"
}
```

Expected procedure steps:

1. Open a `restart_service` request through the MCP gateway.
2. Wait for `PENDING` approval state.
3. Have an authorized human approve the request.
4. Execute the approved operation once.
5. Verify service state and audit event.

The document output includes:

```text
Fictional/demo engineering documentation for the simulator environment. Not actual company documentation.
```

## DEMO 4 - Ticket Automation

Prompt:

```text
Create a maintenance ticket for SIM-014.
```

Expected MCP tool:

| Tool | Risk | Permission | Decision |
| --- | --- | --- | --- |
| `create_ticket` | `MEDIUM` | `tickets:create` | `ALLOWED` |

Expected ticket:

```json
{
  "ticket_id": "TCK-d55ab69c",
  "title": "Maintenance ticket for SIM-014 network timeout",
  "device_id": "SIM-014",
  "priority": "CRITICAL",
  "status": "OPEN",
  "team": "Simulator Operations"
}
```

Expected audit record:

```json
{
  "actor_id": "operator-1",
  "actor_role": "OPERATOR",
  "tool_name": "create_ticket",
  "risk_level": "MEDIUM",
  "authorization_result": "ALLOW",
  "execution_status": "SUCCEEDED"
}
```

## DEMO 5 - High-Risk Operation

Prompt:

```text
Restart the affected service.
```

Expected governance:

| Item | Expected Value |
| --- | --- |
| Tool | `restart_service` |
| Risk | `HIGH` |
| Required permission | `devices:operate` |
| Requesting principal | `operator-1` |
| Approval principal | `admin-1` |
| Approval ID | `11a1704f-6ca6-51fd-b4ad-1f34e65f006a` |
| Initial status | `PENDING` |
| Final status | `EXECUTED` |

Expected pending approval:

```json
{
  "approval_id": "11a1704f-6ca6-51fd-b4ad-1f34e65f006a",
  "tool_name": "restart_service",
  "risk_level": "HIGH",
  "status": "PENDING",
  "requester_id": "operator-1"
}
```

Expected human approval:

```json
{
  "ok": true,
  "decision": "ALLOWED",
  "data": {
    "approval_status": "APPROVED",
    "approved_by": "admin-1"
  }
}
```

Expected execution result:

```json
{
  "device_id": "SIM-014",
  "operation": "restart_service",
  "service_name": "telemetry-agent"
}
```

Expected post-execution service state:

```json
{
  "device_id": "SIM-014",
  "service_name": "telemetry-agent",
  "state": "RUNNING"
}
```

Expected audit transitions:

| Transition | Actor | Status |
| --- | --- | --- |
| `approval.requested` | `operator-1` | `PENDING` |
| `restart_service` | `operator-1` | `PENDING_APPROVAL` |
| `approval.approved` | `admin-1` | `APPROVED` |
| `approval.executed` | `operator-1` | `EXECUTED` |
| `restart_service` | `operator-1` | `SUCCEEDED` |

## Supporting Diagrams And Inventory

- [System architecture](architecture/system-architecture.md)
- [Security model](architecture/security-model.md)
- [Approval workflow](architecture/approval-workflow.md)
- [MCP tool inventory](architecture/mcp-tool-inventory.md)
