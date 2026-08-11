# ADR 0001: Monorepo and Service Boundaries

## Status

Accepted

## Context

The platform must demonstrate distributed backend architecture without spreading shared contracts across disconnected repositories.

## Decision

Use a monorepo with `apps`, `services`, `packages`, `infra`, `docs`, and `tests`. Runtime services remain independently deployable. Shared schemas, auth, policy, observability, and common configuration live under `packages`.

## Consequences

Developers can evolve contracts and services together while keeping deployment boundaries explicit. CI must prevent shared package changes from silently breaking services.

