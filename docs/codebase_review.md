# Codebase Review Notes (2026-04-14)

This memo summarizes a quick architecture + implementation review of the current repository.

## What looks strong

1. **Architecture intent is clear and documented.**
   The ADR set defines bounded contexts, durable-vs-ephemeral transport, and the single-container migration strategy clearly.
2. **Runtime design matches the migration phase.**
   Running API + workers + subscriber in one container keeps operational overhead low while context boundaries are still being stabilized.
3. **Event reliability mechanisms are already present.**
   Redis Streams helper includes consumer groups, stale-claim recovery, retries, and DLQ routing.
4. **API follows a sensible cache-first pattern.**
   The analysis endpoint avoids expensive inline computation and pushes refreshes into async event flow.

## Gaps and risks

1. **Docs contain legacy naming that no longer maps 1:1 to code layout.**
   `walkthrough.md` references older paths (`NewsSentiment/...`, `Derivatives/...`) that are not the current package structure.
2. **Context boundary drift risk from compatibility shims.**
   `app/domain/api/*` and `app/domain/sentiment/*` currently proxy into newer packages. Useful for migration, but should have explicit deprecation timeline to avoid permanent dual namespaces.
3. **Observability depth is still early-stage.**
   Logging exists, but there is no obvious metrics/tracing instrumentation for lag, DLQ rate, freshness SLO, or per-context throughput.
4. **Freshness policy is hardcoded in service layer.**
   Staleness thresholds in `AnalysisService` are static constants; these should likely be environment-configurable to tune behavior by market regime.

## Suggested priority sequence

1. **Documentation alignment pass (high leverage).**
   Update `walkthrough.md` to the current module paths and note which files are compatibility aliases.
2. **Migration governance hardening.**
   Add a dated plan for removing `app/domain/api` and `app/domain/sentiment` aliases after consumer cutover.
3. **Operational telemetry baseline.**
   Add metrics for stream lag, pending messages, DLQ growth, refresh request rate, and API stale/partial response percentages.
4. **Config externalization.**
   Move staleness thresholds and retry/claim intervals to env-driven settings with sane defaults.

## Overall view

The project is in a good transitional state: the architecture decisions are sound and many of the difficult event-driven reliability concerns are already implemented. The biggest near-term wins are **documentation/runtime alignment** and **observability hardening**, so the team can safely accelerate toward multi-service extraction when exit criteria are met.

## Progress update (this change set)

- `walkthrough.md` was rewritten to align with the current bounded-context package layout and active runtime process model.
- Legacy duplicate topic document `docs/event-topics.md` was removed in favor of `docs/EVENT_TOPICS.md` as canonical source.
