# Security

## Trust Boundary

**AI recommends. Policy authorizes. Human approves. MCP executes. Audit records.**

LLM output is treated as untrusted proposal data. It cannot set `authorized=true`, lower risk levels, disable approval, invent valid tools, or override policy. Tool output and RAG content are also untrusted evidence and are wrapped separately from trusted instructions.

## Authentication And RBAC

Roles:

- `VIEWER`: read devices, knowledge, and tickets.
- `ENGINEER`: viewer permissions plus diagnostics and ticket mutation.
- `OPERATOR`: engineer permissions plus device operation request capability.
- `ADMIN`: approval authority according to policy, with self-approval blocked.

The production gateway path validates signed JWTs server-side. Demo tokens exist for deterministic tests and local flows, but production gateway tests verify default demo auth is rejected in production mode.

## Tool Governance

Every registered tool has trusted metadata:

- name, server, domain, category, tags
- JSON input schema
- required permission and roles
- risk level: `READ_ONLY`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`
- approval requirement
- timeout and rate limit
- idempotency/retry/compensation metadata
- metadata fingerprint and server trust level

Registration rejects duplicate/conflicting identities, unsafe schemas, suspicious instruction-like descriptions, malformed metadata, and unexpected poisoning patterns.

## Approval Security

Approvals are bound to:

- workflow ID
- node ID
- tool name
- argument hash
- requester
- approver
- expiration

The system blocks self-approval, duplicate approval, approval replay, approval after expiry, modified-argument reuse, and execution without approval. Policy is re-evaluated immediately before execution to prevent stale decisions.

## Sensitive Data

Structured logging sanitizes passwords, JWTs, API keys, database credentials, bearer tokens, and secret-like values. Audit records retain metadata and argument hashes rather than raw sensitive inputs.

## Error Handling

API validation and HTTP errors use structured JSON:

```json
{
  "ok": false,
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "details": []
  }
}
```

## Tested Security Controls

The test suite covers unauthorized tool calls, role escalation attempts, model-supplied authorization bypass, high-risk approval routing, self-approval denial, replay protection, hallucinated tools, prompt injection in tool descriptions/output/docs, argument tampering, production action denial, log redaction, and gateway audit records.

## Residual Risks

- Prompt-injection handling is layered risk reduction, not a claim of perfect prevention.
- Local Docker Compose is not a hardened production deployment.
- Enterprise OIDC/JWKS integration should be connected to the existing JWT authenticator boundary for a real pilot.
