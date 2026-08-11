# Approval Workflow Diagram

```mermaid
stateDiagram-v2
    [*] --> ToolRequest
    ToolRequest --> Authorized: authn, RBAC, policy metadata
    Authorized --> PENDING: HIGH or CRITICAL risk requires approval
    PENDING --> APPROVED: authorized human approver
    PENDING --> REJECTED: authorized human rejection
    PENDING --> EXPIRED: approval TTL elapsed
    APPROVED --> EXECUTED: matching approved request executes once
    APPROVED --> FAILED: execution error
    EXECUTED --> [*]
    REJECTED --> [*]
    EXPIRED --> [*]
    FAILED --> [*]
```

## Phase 13 Instance

| Transition | Actor | Audit Result |
| --- | --- | --- |
| `restart_service` requested | `operator-1` | `PENDING_APPROVAL` |
| `approval.requested` | `operator-1` | `PENDING` |
| `approval.approved` | `admin-1` | `APPROVED` |
| `approval.executed` | `operator-1` | `EXECUTED` |
| `restart_service` result | `operator-1` | `SUCCEEDED` |

The deterministic demo approval ID is
`11a1704f-6ca6-51fd-b4ad-1f34e65f006a`.
