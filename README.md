# AlphaStreams V2 — Event-Driven Quantitative Analytics using NLP and ML

A Python-based **Event-Driven Modular Monolith** that combines **Financial News Sentiment** (scored by FinBERT AI) with **Real-Time F&O Options Analytics** to generate complete market overviews and real-time streaming updates.

Built with **FastAPI, Celery, Redis Streams + Pub/Sub, TimescaleDB, and PyTorch**.

---

## 🛠 Tech Stack

### Backend Infrastructure

*   **Language:** Python 3.11+ (Asynchronous)
*   **Web Framework:** [FastAPI](https://fastapi.tiangolo.com/) (ASGI) with Uvicorn
*   **Task Queue:** [Celery](https://docs.celeryq.dev/en/stable/) (Distributed Task Management)
*   **Real-time Engine:** [WebSockets](https://fastapi.tiangolo.com/advanced/websockets/) for live push-notifications
*   **Monitoring:** [Flower](https://flower.readthedocs.io/en/latest/) (Real-time task dashboard)

### Databases & Messaging

*   **Time-Series DB:** [TimescaleDB](https://www.timescale.com/) (PostgreSQL 15) for high-performance tick storage
*   **In-Memory Store:** [Redis 7](https://redis.io/) (Used as Cache, Message Broker, and Event Bus)
*   **Messaging:** Redis Streams (durable) + Redis Pub/Sub (ephemeral live fan-out)

### AI & Machine Learning

*   **Deep Learning:** [PyTorch](https://pytorch.org/) (Custom 1D-CNN for Quant forecasting)
*   **NLP / LLM:** [HuggingFace Transformers](https://huggingface.co/docs/transformers/index) (FinBERT for narrative analysis)
*   **Feature Engineering:** [Pandas](https://pandas.pydata.org/), [NumPy](https://numpy.org/), and [SciPy](https://scipy.org/)

### Data Sources

*   **Market History:** [yfinance](https://github.com/ranaroussi/yfinance) (Yahoo Finance API)
*   **News Intelligence:** [NewsAPI](https://newsapi.org/) (Global financial headline streaming)
*   **Derivative Data:** Native NSE India Scraping/API Integration

### DevOps

*   **Containerization:** Docker & Docker Compose
*   **Architecture:** Domain-Driven Design (DDD) Modular Monolith

---

## 💡 Architecture (Current Runtime)

The codebase is aligned to a **3-domain DDD modular monolith** with explicit context boundaries:

1. **`ingestion`**
   * Polls external market/news sources.
   * Publishes canonical ingestion events.
2. **`nlp_logic`**
   * Consumes ingestion events from durable streams.
   * Runs FinBERT scoring, timeframe aggregation, and ML cache updates.
3. **`frontend_api`**
   * Exposes REST + WebSocket interfaces.
   * Serves read models and avoids heavy NLP in request paths.

### Single-container runtime (actual deployment)

`docker-compose.yml` runs one **`app` container** for all core processes, launched by `scripts/entrypoint_single_container.sh`:

* FastAPI (`uvicorn app.main:App`)
* Celery ingestion worker (`-Q ingestion`)
* Celery beat scheduler
* NLP stream subscriber (`python -m app.domain.sentiment.event_subscriber`)

Redis and Postgres run as supporting containers.

---

## 📡 Event Model (Durable-first)

Cross-domain correctness uses **Redis Streams** (durable, replayable, consumer-group semantics). Pub/Sub is used only for UX/live push.

### Durable streams (state/correctness path)

| Stream | Producer domain | Consumer domain | Notes |
|---|---|---|---|
| `stream:headlines.fetched` | ingestion | nlp_logic | Canonical fetched headlines. |
| `stream:market.price_trigger` | ingestion | nlp_logic | Triggered market anomalies. |
| `stream:sentiment.scored` | nlp_logic | downstream/read-model consumers | Per-headline sentiment result. |
| `stream:sentiment.aggregate_updated` | nlp_logic | frontend_api read-model consumers | Timeframe aggregates. |
| `stream:analysis.refresh_requested` | frontend_api | ingestion | Async refresh command path. |

### Ephemeral Pub/Sub mirrors (UX-only)

| Channel pattern | Purpose |
|---|---|
| `headlines.fetched.{symbol}` | Live headline notifications. |
| `market.price_updated.{symbol}` | Live price updates. |
| `market.options_updated.{symbol}` | Live options summary updates. |
| `market.price_trigger.{symbol}` | Live trigger notifications. |
| `sentiment.scored.{symbol}` | Live scored-sentiment fan-out. |
| `sentiment.aggregate_updated.{symbol}` | Live aggregate fan-out. |

**Policy:** publish critical events to durable streams first; Pub/Sub mirrors are non-replayable and not correctness-critical.

---

## 🧯 Operational runbooks

* Startup runbook: [`docs/runbooks/startup.md`](docs/runbooks/startup.md)
* Failure & recovery runbook: [`docs/runbooks/failure-recovery.md`](docs/runbooks/failure-recovery.md)

## 🚀 Getting Started

This system is completely dockerized. All configurations are driven via the `.env` file.

1.  **Copy the Environment Template**

    ```bash
    cp .env.template .env
    ```

    Add your `NEWS_API_KEY` to `.env`.

2.  **Start the Infrastructure**

    ```bash
    docker compose up -d
    ```

    *Note: PyTorch initializes securely in CPU mode to drastically reduce Docker image size requirements by bypassing heavy CUDA dependencies.*

3.  **Initialize the Database Schema**

    *(First Boot Only)*

    ```bash
    docker compose cp scripts/init_schema.sql postgres:/tmp/init_schema.sql
    docker compose exec postgres psql -U postgres -d NexusQuantDB -f /tmp/init_schema.sql
    ```

---

## 🧪 Interactive API Testing

The Celery scheduler and Sentiment subscribers run autonomously in the background! As data flows in, you can query the API.

### 1. Unified Analysis Report (REST)

Returns the live options chain surface, current price, latest headlines, and the multi-timeframe FinBERT aggregations for any symbol.

```bash
curl http://localhost:8000/v1/analyze/NIFTY
```

### 2. Live WebSocket Streaming (Push)

Using a websocket client (e.g. VS Code Bruno or Postman), connect to:
`ws://localhost:8000/ws/NIFTY`
Events will spontaneously push to you whenever new prices, options, headlines, or sentiment updates enter the architecture!

> [!NOTE]
> **On Closed Markets**: Rather than crashing or blank-screening, the system gracefully degrades outside of NSE trading hours (9:15 AM – 3:30 PM IST), relying on Redis closures and asynchronous persistence to serve the last-known "CLOSED" state, while continuing to poll 24/7 web news APIs for weekend sentiment!
