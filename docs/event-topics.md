# Event Topics: Durable vs Ephemeral

This document lists concrete topic transport guarantees in the current implementation.

## Durable topics (Redis Streams)

These are replayable and processed with consumer-group semantics (offsets, `XACK`, retries, DLQ).

### Ingestion -> NLP

- `stream:headlines.fetched`
- `stream:market.price_trigger`

Consumer group:

- `cg:ingestion_to_nlp` (used by the sentiment subscriber)

DLQ:

- `stream:dlq:ingestion_to_nlp`

### NLP -> API/read models

- `stream:sentiment.scored`
- `stream:sentiment.aggregate_updated`

DLQ:

- `stream:dlq:nlp_to_api`

## Ephemeral topics (Redis Pub/Sub)

These are non-replayable and intended for live websocket fan-out only.

- `headlines.fetched.{symbol}`
- `market.price_updated.{symbol}`
- `market.options_updated.{symbol}`
- `market.price_trigger.{symbol}`
- `sentiment.scored.{symbol}`
- `sentiment.aggregate_updated.{symbol}`

## Publishing policy

1. Publish critical state-changing events to durable streams first.
2. Optionally mirror those events to Pub/Sub for UX-only websocket freshness.
3. Do not build correctness-critical read models from Pub/Sub delivery.
