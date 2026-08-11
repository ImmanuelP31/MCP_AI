# ADR 0002: MCP Gateway as Policy Enforcement Point

## Status

Accepted

## Context

The AI agent must not bypass authorization, approval, audit, or tool registry controls.

## Decision

The agent calls only the MCP gateway. The gateway consults the central tool registry, evaluates RBAC and policy, creates approvals for high-risk operations, enforces idempotency and rate limits, calls domain MCP servers, and records audit events.

## Consequences

Domain MCP servers can focus on domain behavior, but high-risk tools must still require an approved execution context from the gateway as defense in depth.

