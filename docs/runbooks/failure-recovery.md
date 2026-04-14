# Runbook: Failure Modes and Recovery

This runbook documents expected failure behavior for the durable-stream event model and single-container process supervisor script.

## Runtime behavior summary

- `scripts/entrypoint_single_container.sh` starts four child processes.
- If **any** child exits, the script stops remaining children and exits non-zero.
- Docker Compose `restart: unless-stopped` restarts the `app` container.

This provides whole-container fail-fast behavior with automatic restart.

---

## Failure modes

## 1) App child process crash (API / worker / beat / NLP subscriber)

### Symptoms

- `app` container restarts repeatedly.
- `docker compose logs app` shows: `a child process exited with code ...`.

### Immediate checks

```bash
docker compose ps
docker compose logs --tail=200 app
```

### Recovery

1. Identify failing child from logs.
2. Fix config/runtime issue (credentials, unavailable dependency, bad code deploy).
3. Restart stack:

```bash
docker compose up -d
```

4. Confirm `/health` and event processing logs recover.

---

## 2) Redis unavailable or intermittent

### Symptoms

- Celery worker cannot connect to broker/backend.
- NLP subscriber fails reads/writes to streams.
- API responses may degrade when cache access fails.

### Checks

```bash
docker compose ps
docker compose logs --tail=200 redis
docker compose logs --tail=200 app
```

### Recovery

1. Restore Redis container health.
2. Let `app` container restart or manually restart it.
3. Validate consumer groups resume processing.

Notes:

- Durable streams preserve pending messages while consumers are down.
- Pub/Sub mirrors are lossy; missed live pushes are expected during outage windows.

---

## 3) Postgres unavailable

### Symptoms

- Ingestion or NLP writes fail (TickData/SentimentScores inserts).
- API may return partial responses when backing reads fail.

### Checks

```bash
docker compose ps
docker compose logs --tail=200 postgres
docker compose logs --tail=200 app
```

### Recovery

1. Restore Postgres health.
2. Ensure schema exists (run init SQL if DB was recreated).
3. Restart `app` if needed.
4. Verify new writes succeed in logs.

---

## 4) Poison messages / handler exceptions

### Behavior

Durable consumer handlers use retry + DLQ logic:

- Failed messages are requeued with incremented retry count.
- After max retries, message is sent to:
  - `stream:dlq:ingestion_to_nlp`, or
  - `stream:dlq:nlp_to_api`.
- Original message is acknowledged after DLQ handoff.

### Checks

Use Redis CLI inside container:

```bash
docker compose exec redis redis-cli XLEN stream:dlq:ingestion_to_nlp
docker compose exec redis redis-cli XLEN stream:dlq:nlp_to_api
```

### Recovery

1. Fix root cause (schema mismatch, bad payload assumptions, transient dependency issues).
2. Replay from DLQ only after fix validation.
3. Track replay window and verify duplicate-safe behavior where applicable.

---

## 5) Consumer lag / stale pending entries

### Behavior

Consumers periodically call `XAUTOCLAIM` for stale pending messages (`*_RETRY_IDLE_MS` thresholds) to recover abandoned work.

### Checks

```bash
docker compose exec redis redis-cli XINFO GROUPS stream:headlines.fetched
docker compose exec redis redis-cli XINFO GROUPS stream:market.price_trigger
docker compose exec redis redis-cli XINFO GROUPS stream:sentiment.aggregate_updated
```

Watch `pending` and `lag` values.

### Recovery

1. Scale/fix consumer throughput bottleneck.
2. Keep consumers running until pending counts normalize.
3. If needed, restart `app` container to recycle stuck worker state.

---

## Recovery validation checklist

After any incident, verify:

1. `docker compose ps` shows healthy `app`, `redis`, `postgres`.
2. `curl http://localhost:8000/health` returns `status=ok`.
3. `app` logs show ingestion tasks and NLP subscriber consuming streams.
4. DLQ growth has stopped (unless actively replaying).
5. Fresh symbol analysis requests return current data and no sustained error envelope spikes.
