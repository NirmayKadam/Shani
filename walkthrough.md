# AlphaStreams — Project Walkthrough & Onboarding (Current Runtime)

This walkthrough reflects the **current codebase layout** and runtime behavior in this repository.

## 1) What the system does

AlphaStreams is an event-driven analytics backend that combines:

- **Market ingestion** (prices, options, headlines)
- **NLP processing** (FinBERT sentiment + timeframe aggregates)
- **Frontend delivery** (REST analysis + WebSocket fan-out)

The current deployment model is a **single application container** running API and background processes together during the migration phase.

## 2) Active bounded contexts

### `ingestion`
- Polls news, market prices, and option-chain snapshots.
- Writes hot cache/read-model data where appropriate.
- Publishes durable stream events for downstream consumers.

Primary module:
- `app/domain/ingestion/application/tasks.py`

### `nlp_logic`
- Consumes durable ingestion events via Redis Streams consumer groups.
- Scores headlines with FinBERT.
- Recomputes timeframe aggregates and publishes durable aggregate events.

Primary module:
- `app/domain/nlp_logic/infrastructure/event_subscriber.py`

### `frontend_api`
- Exposes cache-first query endpoints.
- Publishes async refresh requests when responses are stale/partial.
- Maintains websocket live updates using Pub/Sub mirrors.

Primary modules:
- `app/domain/frontend_api/interfaces/routers/analyze.py`
- `app/domain/frontend_api/interfaces/routers/websocket.py`
- `app/domain/frontend_api/application/services/analysis_service.py`
- `app/domain/frontend_api/infrastructure/read_model_updater.py`

## 3) Runtime processes (single-container)

The app container starts these child processes via `scripts/entrypoint_single_container.sh`:

1. FastAPI (`uvicorn app.main:App`)
2. Celery ingestion worker (`-Q ingestion`)
3. Celery beat scheduler
4. NLP stream subscriber (`python -m app.domain.sentiment.event_subscriber`)

> Note: `app.domain.sentiment.event_subscriber` is a compatibility alias forwarding to `app.domain.nlp_logic.infrastructure.event_subscriber`.

## 4) Event transport model

### Durable streams (correctness path)
- `stream:headlines.fetched`
- `stream:market.price_trigger`
- `stream:sentiment.scored`
- `stream:sentiment.aggregate_updated`
- `stream:analysis.refresh_requested`

### Ephemeral Pub/Sub (UX fan-out)
- `headlines.fetched.{symbol}`
- `market.price_updated.{symbol}`
- `market.options_updated.{symbol}`
- `market.price_trigger.{symbol}`
- `sentiment.scored.{symbol}`
- `sentiment.aggregate_updated.{symbol}`

For complete producer/consumer and schema mapping, see `docs/EVENT_TOPICS.md`.

## 5) Request path summary (`GET /v1/analyze/{symbol}`)

1. API validates symbol against configured watchlist.
2. Analysis service reads market/headline/sentiment/options/forecast from Redis-first read models.
3. If data is stale or partial, API still returns quickly and publishes an async refresh request (`stream:analysis.refresh_requested`).
4. Ingestion + NLP flows continue asynchronously and update caches/read-models consumed by API and websocket clients.

## 6) Compatibility aliases (temporary migration layer)

The following paths exist as compatibility shims and currently re-export the new module locations:

- `app/domain/api/*` -> `app/domain/frontend_api/*`
- `app/domain/sentiment/*` -> `app/domain/nlp_logic/*`

These should be removed once all runtime/tooling references are migrated.

## 7) Suggested onboarding order

1. Read `README.md` for architecture + startup.
2. Read `docs/adr/ADR-001-bounded-contexts.md` and `docs/adr/ADR-002-event-transport.md`.
3. Read `app/shared/event_bus/contracts.py` and `app/shared/event_bus/streams.py`.
4. Read ingestion tasks and NLP subscriber modules.
5. Read frontend API service/router modules.
6. Use runbooks in `docs/runbooks/` for ops workflows.
