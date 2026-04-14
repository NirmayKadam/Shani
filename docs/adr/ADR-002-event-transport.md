# ADR-002: Event Transport (Durable vs Ephemeral Topics)

- **Status:** Accepted
- **Date:** 2026-04-14
- **Decision Makers:** Architecture group

## Context

The platform requires both replayable event streams (for correctness and recovery) and low-latency transient notifications (for UX freshness). A single transport policy does not fit both needs.

## Decision

Adopt two topic classes in the event transport layer:

## 1) Durable topics

Use for business-critical events that require retention and replay.

- Typical usage:
  - `ingestion.raw.normalized`
  - `nlp_logic.sentiment.scored`
  - `nlp_logic.features.derived`
- Requirements:
  - persistent storage/replication
  - consumer offsets/checkpointing
  - retention policy sized for backfills and audit windows

## 2) Ephemeral topics

Use for non-critical, short-lived updates where replay is unnecessary.

- Typical usage:
  - UI refresh hints
  - cache invalidation pings
  - transient progress/status notifications
- Requirements:
  - short TTL
  - no recovery guarantees beyond active subscribers

## Routing Rules

- Domain state changes must be published to **durable** topics first.
- Derived live notifications may be mirrored to **ephemeral** topics.
- `frontend_api` can subscribe to both, but read-model correctness must depend only on durable streams.

## Consequences

- **Positive:** supports reliable processing and responsive UX simultaneously.
- **Trade-off:** more topic governance and observability responsibilities.
- **Risk:** accidental publishing of critical events to ephemeral channels; mitigated via naming conventions and CI topic policy checks.
