# ADR-003: Single-Container Runtime

- **Status:** Accepted
- **Date:** 2026-04-14
- **Decision Makers:** Platform and architecture groups

## Context

For early migration phases, operational complexity should remain low while boundaries are still being established. Running many services too early increases orchestration and debugging overhead.

## Decision

Use a **single-container runtime** during the migration transition period:

- One deployable container hosts `ingestion`, `analytics`, and `app` modules.
- Modules remain logically separated in code and runtime wiring.
- Internal communication can use in-process adapters that preserve event contracts.

## Guardrails

- Keep module boundaries explicit (separate packages/directories and interfaces).
- Maintain transport abstraction so external brokers can be enabled later without contract changes.
- Track per-module metrics/log fields to preserve operational visibility.

## Exit Criteria

Move to multi-service deployment when at least one of the following is true:

1. Throughput or latency requires independent scaling.
2. Team ownership requires separate deploy cadence.
3. Fault isolation requirements exceed in-container boundaries.

## Consequences

- **Positive:** simpler deployment, faster iteration, easier local development.
- **Trade-off:** weaker runtime isolation and potential noisy-neighbor effects.
- **Risk:** boundary erosion if convenience shortcuts bypass interfaces; mitigated by architecture tests and code owners.
