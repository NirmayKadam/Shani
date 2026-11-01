# Contributing to AlphaStreams V2

Thank you for your interest in contributing! This document provides guidelines for development workflows.

---

## Development Setup

### Prerequisites

- Python 3.11+
- Docker & Docker Compose

### Local Development

1. **Clone the repo**
   ```bash
   git clone https://github.com/NirmayKadam/Shani.git
   cd Shani
   ```

2. **Create environment file**
   ```bash
   cp .env.example .env
   # Configure MARKET_DATA_PROVIDER and any adapter credentials in .env
   ```

3. **Start the container**
   ```bash
   docker compose up -d
   ```

4. **View logs**
   ```bash
   docker compose logs -f app
   ```

5. **Access the app**  
   Open [http://localhost:8000](http://localhost:8000)

---

## Project Architecture

This is a **Modular Monolith** following Domain-Driven Design (DDD) principles:

```
domains/
├── ingestion/       # Fetches data from external sources (Groww, NSE, yfinance)
├── analytics/       # Technical indicators, BSM & PDE options pricing, read-model updates
├── notifications/   # Real-time alert rules, event matching, and dispatch channels
```

Cross-domain communication uses **Redis Streams** (durable events). See `shared/infrastructure/event_bus/` for contracts.

Market data ingestion uses a **pluggable adapter factory** (`adapter_factory.py`) that selects the provider based on `MARKET_DATA_PROVIDER` env var. Each adapter implements `IMarketPriceSourcePort` and `IOptionChainSourcePort`.

---

## Code Style

- **Python**: Follow PEP 8. Use type hints for function signatures.
- **Logging**: Use `logging.getLogger(__name__)` — never `print()`.
- **Async**: All FastAPI endpoints and Redis operations should be `async`.
- **Domain boundaries**: Never import directly between `ingestion` and `analytics` domains. Use events.
- **Zero Mock / Synthetic Data Policy**: Never insert fake prices, synthetic fallback ticks, or mock responses in domain, API, or infrastructure code. System must fail fast (`HTTP 503 Service Unavailable` or custom exceptions) or render explicit unavailable UI states when live data/services fail.

---

## Adding a New API Endpoint

1. Create a new router file in `domains/analytics/api/` (or `domains/ingestion/api/`).
2. Define Pydantic schemas in `schemas.py`.
3. Register the router in `app/main.py`.
4. Add an entry to `docs/api.md`.

---

## Adding a New Market Data Provider

1. Create a new adapter in `domains/ingestion/infrastructure/outbound/` (e.g., `zerodha_api_adapter.py`).
2. Implement both `IMarketPriceSourcePort` and `IOptionChainSourcePort` interfaces.
3. Add a fallback to `NseApiAdapter` for resilience (see `GrowwApiAdapter` as reference).
4. Register the provider in `adapter_factory.py` with a new `MARKET_DATA_PROVIDER` value.
5. Add any required credentials to `app/config/settings.py` (`Settings` class) and `.env.example`.
6. Write unit tests in `tests/unit/test_<provider>_adapter.py`.

---

## Adding a New Stream Event

1. Define the event contract in `shared/infrastructure/event_bus/contracts.py`.
2. Register the stream name in `shared/constants.py` under the `Streams` class.
3. Add Pub/Sub channel in `shared/constants.py` under the `Channels` class (if UX push is needed).
4. Publish with `DurableEventStream.publish` (length-bounded `XADD`); add a dead-letter stream (`*_DLQ`) and a consumer group in `StreamGroups`.
5. Consume with `run_durable_consumer` (`shared/infrastructure/event_bus/consumer.py`): it acknowledges after handling, retries, dead-letters and reclaims stalled messages. Handlers must be idempotent, because a message can be delivered more than once.

---

## Testing

```bash
# Unit tests (default: integration and live tests are skipped, and startup network calls are mocked)
python -m pytest

# Tests that need Redis/Postgres
python -m pytest -m integration

# Tests that call external APIs (NSE, yfinance)
python -m pytest -m live
```

### Test Coverage

| Category | Files (`tests/unit/` unless noted) |
|---|---|
| **Adapters & ingestion** | `test_groww_api_adapter.py`, `test_nse_api_adapter.py`, `test_ingestion_service.py`, `test_market_time.py`, `test_market_status.py` |
| **Pricing** | `test_black_scholes.py`, `test_pde_solver.py` (accuracy grid, batched parity), `test_options_subscriber.py`, `test_pricer_router_api.py`, `test_pcr_and_technicals.py`, `test_volatility_surface.py` |
| **Notifications** | `test_notification_domain.py`, `test_rule_matcher.py`, `test_notification_subscriber.py`, `test_channels.py` |
| **Security** | `test_security.py` (JWT verification, alert ownership, WebSocket routing, SSRF guard) |
| **Reliability & performance** | `test_durable_consumer.py`, `test_backend_caching.py`, `test_events_router_api.py` |
| **Other** | `test_symbol_validator.py`, `test_analytics_domain.py`, `test_ohlc_historical.py`, `test_historical_research_exporter.py` |
| **Integration** | `tests/integration/`: `test_alert_repository.py`, `test_api_endpoints.py`, `test_derivatives_pipeline.py`, `test_notifications_api.py`; `tests/e2e/test_notifications_pipeline.py` |

The unit suite has 196 tests and runs in about 15 seconds. When adding a new adapter or service, add corresponding tests following the existing patterns in `tests/conftest.py` for shared fixtures.

---
## Database Migrations

Schema changes go in `scripts/init_schema.sql` or a new `scripts/migration_*.sql` file. `scripts/migrate.py` applies them on every container start. To apply by hand:

```bash
docker compose exec app psql -U postgres -d NexusQuantDB -f /app/scripts/init_schema.sql
```

> For additive migrations (new columns, new tables), create a separate migration file in `scripts/` (e.g., `migration_add_xyz.sql`).

---

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add volatility surface chart endpoint
fix: resolve BSM pricing edge case for deep OTM options
docs: update API reference with pricer endpoints
refactor: extract symbol validation into shared utility
```

---

## Performance Guidelines

- **Celery Tasks**: Use `_get_or_create_loop()` from `ingestion_tasks.py` for persistent event loops. Never call `asyncio.run()` — it creates and destroys a loop per invocation.
- **Connection Pools**: Redis clients, asyncpg pools and market adapters are cached **per event loop** (`get_redis_client()`, `get_database_pool()`, `get_market_data_adapter()`). Don't close a shared adapter, and don't share a client across loops.
- **Static Data Caching**: Cache slow-changing data (e.g., dividend yields) in Redis with appropriate TTLs. Examples: Groww token and expiry list (`GrowwApiAdapter`), technicals history (`derivatives_router_api._daily_history`). Never cache failures.
- **uvloop**: The production container uses `uvloop` for the FastAPI server (`--loop uvloop`). This is Linux-only and ignored on Windows.
- **CPU-bound work**: Offload to the pricing `ProcessPoolExecutor` (spawn start method), not `asyncio.to_thread`: threads share the GIL, so pure-Python loops don't run in parallel.
