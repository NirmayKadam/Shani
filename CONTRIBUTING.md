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
├── ingestion/     # Fetches data from external sources (NSE, NewsAPI, yfinance)
├── analytics/     # NLP scoring, ML forecasting, options pricing, read-model updates
```

Cross-domain communication uses **Redis Streams** (durable events). See `shared/infrastructure/event_bus/` for contracts.

---

## Code Style

- **Python**: Follow PEP 8. Use type hints for function signatures.
- **Logging**: Use `logging.getLogger(__name__)` — never `print()`.
- **Async**: All FastAPI endpoints and Redis operations should be `async`.
- **Domain boundaries**: Never import directly between `ingestion` and `analytics` domains. Use events.

---

## Adding a New API Endpoint

1. Create a new router file in `domains/analytics/api/` (or `domains/ingestion/api/`).
2. Define Pydantic schemas in `schemas.py`.
3. Register the router in `app/main.py`.
4. Add an entry to the API Reference section in `README.md`.

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
# Run unit tests
docker compose exec app python -m pytest tests/unit/ -v

# Run integration tests
docker compose exec app python -m pytest tests/integration/ -v
```

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
