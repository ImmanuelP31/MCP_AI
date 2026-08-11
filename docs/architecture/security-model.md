# Security Model Diagram

```mermaid
flowchart TD
    Request["Tool request\nfrom UI or AI agent"]
    AuthN["Authenticate token\nserver-side principal"]
    Registry["Lookup tool metadata\nrisk, permission, enabled, timeout, rate limit"]
    RBAC["RBAC permission check"]
    Validate["Strict schema validation\nstrip untrusted actor/risk fields"]
    Rate["Rate limit check"]
    Idempotency["Idempotency reservation"]
    Approval{"Requires approval?"}
    Pending["Create PENDING approval\nno execution"]
    Dispatch["Dispatch to domain MCP server"]
    Audit["Append audit record"]
    Deny["Deny with structured error"]

    Request --> AuthN
    AuthN --> Registry
    Registry --> RBAC
    RBAC --> Validate
    Validate --> Rate
    Rate --> Idempotency
    Idempotency --> Approval
    Approval -- Yes, no valid approval --> Pending --> Audit
    Approval -- No or approved --> Dispatch --> Audit

    AuthN -- invalid --> Deny --> Audit
    Registry -- unknown or disabled --> Deny
    RBAC -- lacks permission --> Deny
    Validate -- malformed arguments --> Deny
    Rate -- exceeded --> Deny
    Idempotency -- duplicate --> Deny
```

## Controls Demonstrated

| Control | Demo Evidence |
| --- | --- |
| Authentication | `operator-token`, `admin-token`, and `ai-token` resolve server-side principals. |
| Authorization | `restart_service` checks `devices:operate`. |
| AI isolation | The AI agent calls only the MCP gateway. |
| Approval separation | `operator-1` requests; `admin-1` approves. |
| Input validation | Tool arguments are strict Pydantic schemas. |
| Audit | Every allow, pending approval, approval, execution, and denial path writes audit data. |
