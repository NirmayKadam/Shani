# Migration Checklist

This checklist guides migration toward the bounded-context architecture and event transport model while preserving rollback safety.

## 0) Preparation

- [ ] Confirm owners for `ingestion`, `nlp_logic`, and `frontend_api`.
- [ ] Inventory existing pipelines, endpoints, and data contracts.
- [ ] Define success metrics (latency, error rate, freshness, throughput).
- [ ] Freeze non-essential schema changes during cutover windows.

## 1) Establish boundaries in code

- [ ] Create/verify module boundaries for each context.
- [ ] Remove direct cross-domain imports; replace with DTO/event contracts.
- [ ] Add architecture checks/tests to prevent boundary violations.

## 2) Introduce transport classification

- [ ] Create durable topics for critical domain events.
- [ ] Create ephemeral topics for transient UI/cache/status notifications.
- [ ] Add producer policy checks (critical events cannot target ephemeral topics).
- [ ] Document retention/TTL settings and ownership.

## 3) Deploy single-container runtime

- [ ] Build one container including all three contexts.
- [ ] Enable per-context health checks and metrics tags.
- [ ] Configure feature flags for new pipelines and API paths.
- [ ] Verify local and staging startup with representative load.

## 4) Dual-run and validation

- [ ] Run legacy and new flows in parallel (read-only shadow where possible).
- [ ] Compare output parity for sentiment scores and derived features.
- [ ] Validate API response parity and SLO adherence.
- [ ] Capture and resolve drift before traffic cutover.

## 5) Cutover

- [ ] Gradually shift traffic using canary percentages.
- [ ] Monitor error rate, lag, latency, and data freshness.
- [ ] Keep rollback switch and legacy consumers warm during the window.

## 6) Stabilization

- [ ] Remove temporary compatibility shims after a stable period.
- [ ] Update runbooks and on-call alerts.
- [ ] Publish post-migration review with follow-up actions.

## Rollback Notes

If release health degrades beyond agreed thresholds:

1. **Trigger rollback**
   - Flip feature flags to route reads/writes back to legacy paths.
   - Pause new durable-topic consumers to prevent partial writes.

2. **Contain and verify**
   - Confirm legacy pipeline/API health.
   - Validate no data corruption in newly written stores.

3. **Recover state**
   - Replay durable events to rebuild affected read models if required.
   - Purge stale ephemeral notifications/caches.

4. **Communicate and document**
   - Announce rollback status to stakeholders.
   - Record timeline, root cause hypotheses, and next safe retry window.
