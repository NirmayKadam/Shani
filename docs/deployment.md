# Deployment & Operations Guide

AlphaStreams V2 runs in two modes:

- **Local development** (`docker-compose.yml`): one container holding FastAPI, Celery, both stream subscribers, Redis and TimescaleDB, managed by `supervisord`.
- **Production** (`docker-compose.prod.yml`): one service per process, plus a one-shot `migrate` service the API waits for.

---

## 1. Prerequisites

- **Docker** and **Docker Compose** installed.
- A **Supabase** project for sign-in (see section 3).

---

## 2. Configuration Setup

1. Copy the environment template:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env`:
   - **`MARKET_DATA_PROVIDER`** — `groww` for the Groww API or `nse` (default) for the NSE scraper with yfinance fallback.
   - **`GROWW_API_KEY` / `GROWW_API_SECRET` / `GROWW_ACCESS_TOKEN` / `GROWW_TOTP_SECRET`** — only for the Groww provider. Generated access tokens are shared across processes in Redis until they expire.
   - **`supabaseUrl` / `supabaseKey`** — your project URL and **anon** key. `/config` serves these to the browser, so never use the service-role key. `SUPABASE_JWT_SECRET` is needed only for legacy HS256 projects; otherwise tokens are verified against the project's JWKS.
   - **`INTERNAL_API_KEY`** — required in production (`APP_ENV=production`); internal endpoints fail closed without it.
   - **`PRICING_WORKERS`** — processes in the pricing pool (blank = CPU count − 1; compose sets 2).
   - **`SMTP_*`** — only for email alerts. **`WEBHOOK_MAX_ATTEMPTS`** (default 3) and **`WEBHOOK_ALLOW_PRIVATE`** (default false; keep it false outside local testing).
   - **`WS_MAX_CONNECTIONS` / `WS_MAX_SYMBOLS`** — WebSocket admission limits.

---

## 3. Supabase Project Setup

1. Create a project and copy its URL and anon key into `.env`.
2. In the SQL Editor, run `scripts/supabase_schema.sql` (profiles and watchlists with row-level security, plus the signup trigger). It is idempotent.
3. For Google sign-in: create a Google OAuth web client with redirect URI `https://<project-ref>.supabase.co/auth/v1/callback`, then enable **Authentication → Sign In / Providers → Google** with its client ID and secret.
4. **Authentication → URL Configuration:** Site URL `http://localhost:8000` (or your domain) and redirect URL `http://localhost:8000/dashboard.html`.

`scripts/migrate.py` never runs `supabase_schema.sql`; it only migrates the local TimescaleDB.

---

## 4. Starting the System

Local development:
```bash
docker compose up -d
```

Production:
```bash
docker compose -f docker-compose.prod.yml up -d
```

Database migrations (`scripts/migrate.py`) run on **every** start, not only the first, and a failed migration stops startup instead of being ignored.

---

## 5. Operational Processes

In local development, supervisord runs these programs inside the container. Application programs run as the non-root `appuser`; Redis runs as `redis` and Postgres as `postgres`.

| # | Process | Command |
|---|---------|---------|
| 1 | **Redis** | `redis-server --bind 127.0.0.1 --protected-mode yes` |
| 2 | **PostgreSQL 15** (TimescaleDB) | `/usr/lib/postgresql/15/bin/postgres` |
| 3 | **FastAPI** | `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2 --loop uvloop` |
| 4 | **Celery Worker** | `celery -A shared.infrastructure.celery_app:celery_app worker -Q celery,ingestion -c 2` |
| 5 | **Celery Beat** | `celery -A shared.infrastructure.celery_app:celery_app beat -s /tmp/celerybeat-schedule` |
| 6 | **Options Subscriber** | `python3 domains/analytics/infrastructure/options_subscriber.py` (consumer group `cg:options_pricing`) |
| 7 | **Notification Subscriber** | `python3 domains/notifications/infrastructure/subscribers/notification_subscriber.py` (consumer group `cg:alert_evaluation`) |

Polling is driven by the API: while a symbol has WebSocket viewers, exactly one uvicorn worker per interval dispatches the price (5 s) and option-chain (15 s) Celery tasks.

The production compose file runs the same programs as separate services (`api` with 4 workers, `celery_worker`, `celery_beat`, `options_subscriber`, `notification_subscriber`) with Redis append-only persistence.

---

## 6. Connecting to Databases

Postgres and Redis listen only on `127.0.0.1` inside the container; only port 8000 is published. Connect through the container:

```bash
docker compose exec app psql -U postgres -d NexusQuantDB
```

```bash
docker compose exec app redis-cli
```

The application's database role is not a superuser.

---

## 7. Logs, Health & Dead Letters

Application logs:
```bash
docker compose logs -f app
```

`GET /health` reports `degraded` (in every environment) when Redis or the database is unreachable.

Messages that fail processing after their retries are moved to a dead-letter stream. Inspect one with:
```bash
docker compose exec app python scripts/read_dlq.py stream:dlq:options.raw_fetched
```
