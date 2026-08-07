# Contributing to AlphaStreams V2

Thank you for your interest in contributing! This document provides guidelines for development workflows.

---

## Development Setup

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- A [NewsAPI](https://newsapi.org/) key (free tier)

### Local Development

1. **Clone the repo**
   ```bash
   git clone https://github.com/NirmayKadam/MarketSentimentAnalysis2.git
   cd MarketSentimentAnalysis2
   ```

2. **Create environment file**
   ```bash
   cp .env.template .env
   # Add your NEWS_API_KEY to .env
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
├── ingestion/     # Fetches data from external sources (Groww, NSE, NewsAPI, yfinance)
├── analytics/     # Technical indicators, BSM & PDE options pricing, read-model updates
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
4. Add an entry to the API Reference section in `README.md`.

---

## Adding a New Market Data Provider

1. Create a new adapter in `domains/ingestion/infrastructure/adapters/outbound/` (e.g., `zerodha_api_adapter.py`).
2. Implement both `IMarketPriceSourcePort` and `IOptionChainSourcePort` interfaces.
3. Add a fallback to `NseApiAdapter` for resilience (see `GrowwApiAdapter` as reference).
4. Register the provider in `adapter_factory.py` with a new `MARKET_DATA_PROVIDER` value.
5. Add any required credentials to `app/config.py` (`Settings` class) and `.env.template`.
6. Write unit tests in `tests/unit/test_<provider>_adapter.py`.

---

## Adding a New Stream Event

1. Define the event contract in `shared/infrastructure/event_bus/contracts.py`.
2. Register the stream name in `shared/constants.py` under the `Streams` class.
3. Add Pub/Sub channel in `shared/constants.py` under the `Channels` class (if UX push is needed).
4. Implement producer logic in the relevant domain.
5. Implement consumer logic in the target domain.

---

## Testing

```bash
# Run all tests
docker compose exec app python -m pytest tests/ -v

# Run unit tests only
docker compose exec app python -m pytest tests/unit/ -v

# Run integration tests only
docker compose exec app python -m pytest tests/integration/ -v

# Run a specific test file
docker compose exec app python -m pytest tests/unit/test_groww_api_adapter.py -v
```

### Test Coverage

| Category | Files |
|---|---|
| **Adapters** | `test_groww_api_adapter.py`, `test_nse_api_adapter.py` |
| **Services** | `test_ingestion_service.py`, `test_sentiment_analyzer.py`, `test_sentiment_recompute.py` |
| **Pricing** | `test_black_scholes.py`, `test_options_subscriber.py` |
| **Utilities** | `test_symbol_validator.py`, `test_market_status.py` |
| **Pipelines** | `test_api_endpoints.py`, `test_derivatives_pipeline.py`, `test_ingest_pipeline.py` |

When adding a new adapter or service, add corresponding tests following the existing patterns in `tests/conftest.py` for shared fixtures.

---

## Database Migrations

Schema changes go in `scripts/init_schema.sql`. To apply:

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
- **Connection Pools**: Reuse Redis and `aiohttp` sessions via `_get_or_create_service()`. Connections are bound to the event loop that created them.
- **Static Data Caching**: Cache slow-changing data (e.g., dividend yields) in Redis with appropriate TTLs. See `GrowwApiAdapter.fetch_price()` for the pattern.
- **uvloop**: The production container uses `uvloop` for the FastAPI server (`--loop uvloop`). This is Linux-only and ignored on Windows.
