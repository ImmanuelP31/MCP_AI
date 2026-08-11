# ADR 0004: Approval and Audit for High-Risk Tools

## Status

Accepted

## Context

Operations such as service restarts and configuration updates can affect engineering systems and must not run directly from model output.

## Decision

High-risk and critical tools create approval requests before execution. The requester cannot self-approve. Every tool invocation records an audit event with sanitized argument hashes and execution status.

## Consequences

The frontend must show dangerous operations explicitly with target, risk, reason, requester, and approval state. Audit storage is append-oriented and must reject updates except controlled retention or archival operations.

