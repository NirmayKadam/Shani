# Deployment & Operations Guide

AlphaStreams V2 runs in a completely dockerized, single-container setup. All system components (FastAPI, Celery, Redis, TimescaleDB, and PyTorch model weights) are packaged together and orchestrated by `supervisord`.

---

## 1. Prerequisites

- **Docker** and **Docker Compose** installed.
- **NewsAPI Key** (free tier works) from [newsapi.org](https://newsapi.org/).
- Approximately **4 GB of free disk space** for PyTorch and FinBERT transformer model weights.

---

## 2. Configuration Setup

1. Copy the environment template:
   ```bash
   cp .env.template .env
   ```

2. Edit the `.env` file and configure the settings:
   - **`NEWS_API_KEY`** — required for news ingestion.
   - **`MARKET_DATA_PROVIDER`** — set to `groww` for Groww API or `nse` (default) for yfinance/NSE proxy.
   - **`GROWW_API_KEY` / `GROWW_API_SECRET` / `GROWW_ACCESS_TOKEN`** — required if using the Groww provider.

---

## 3. Starting the System

To build and launch the containerized application in background mode:
```bash
docker compose up -d
```

> [!NOTE]
> **First boot** takes 3-5 minutes as the container downloads PyTorch + FinBERT model weights and executes TimescaleDB migrations.

---

## 4. Operational Processes

Supervisord manages the lifecycle of the following processes inside the single container:

| # | Process | Command |
|---|---------|---------|
| 1 | **Redis** | `redis-server` |
| 2 | **PostgreSQL 15** (TimescaleDB) | `/usr/lib/postgresql/15/bin/postgres` |
| 3 | **FastAPI** | `uvicorn app.main:app --host 0.0.0.0 --port 8000 --loop uvloop` |
| 4 | **Celery Worker** | `celery -A shared.infrastructure.celery_app:celery_app worker -Q celery,ingestion,analytics` |
| 5 | **Celery Beat** (Scheduler) | `celery -A shared.infrastructure.celery_app:celery_app beat` |
| 6 | **Sentiment Orchestrator** | `python3 domains/analytics/application/services/nlp/sentiment_orchestrator_service.py` |
| 7 | **Read-Model Updater** | `python3 domains/analytics/application/services/read_model_updater_service.py` |
| 8 | **Ingestion Orchestrator** | `python3 domains/ingestion/application/services/orchestrators/ingestion_orchestrator_service.py` |
| 9 | **Options Subscriber** | `python3 domains/analytics/infrastructure/options_subscriber.py` |

---

## 5. Connecting to Databases

### TimescaleDB (PostgreSQL)
- **Host**: `127.0.0.1`
- **Port**: `5433` (mapped from container `5432` to avoid local host conflicts)
- **Database**: `NexusQuantDB`
- **Username**: `postgres`
- **Password**: `postgres`

### Redis
- **Host**: `127.0.0.1`
- **Port**: `6379`
- **Password**: (None)

---

## 6. Logs & Monitoring

To monitor application logs in real-time:
```bash
docker compose logs -f app
```
