# ADR 0003: Data and Messaging Store Roles

## Status

Accepted

## Context

The platform needs persistence, caching, event processing, and operational log search.

## Decision

Use PostgreSQL as the source of truth, including production gateway approvals, approval transition events, audit records, idempotency keys, and rate-limit windows. Use Redis for short-lived cache and optional runtime acceleration, Kafka for domain events, and OpenSearch for operational logs.

## Consequences

No persistent business data should rely on Redis. Event consumers must be idempotent. Logs in OpenSearch are searchable evidence, not the system of record for approvals or audit.
