# AlphaStreams V2 — Event-Driven Quant Analytics (Indian Market Focus)

A Python-based **Event-Driven Modular Monolith** combining **FinBERT-powered Sentiment Analysis**, **Real-Time NSE/BSE Analytics**, and an **Interactive Option Chain Dashboard** to generate actionable market overviews.

Built with **FastAPI, Celery, Redis Streams, TimescaleDB, PyTorch**, and a **production-grade web UI** modelled after the NSE India option chain interface.

---

## 📖 System Documentation

To read the detailed system documentation, please refer to the following guides:

- 🏗️ **[System Architecture](docs/architecture.md)** — Architectural design, DDD contexts, process layout, and durable event stream schema.
- ⚙️ **[Deployment & Operations](docs/deployment.md)** — Docker setup, system prerequisites, database connection guides, and logs.
- 🔌 **[API Reference](docs/api.md)** — Detailed REST endpoints list and WebSocket real-time message payloads.

---

## Features

- **NSE Option Chain Dashboard** — interactive web UI cloning the NSE India option chain layout, with Calls / Strikes / Puts dual-column table.
- **Client-Side BSM Calculator** — real-time Black-Scholes-Merton pricing, full Greeks (Δ, Γ, ν, θ, ρ), and theoretical edge overlays.
- **Dynamic Instrument Search** — autocomplete search across 2,000+ NSE equities and indices via a live instrument catalog.
- **Real-Time WebSocket Push** — live price ticks, scored sentiment, and options data streamed to the UI.
- **FinBERT NLP Sentiment** — automatic financial headline scoring (BULLISH / BEARISH / NEUTRAL) using ProsusAI/FinBERT.
- **MTF-CNN-LSTM Volatility Prediction** — 5-day forward volatility forecasting (VOL_CRUSH / NEUTRAL / VOL_EXPAND).
- **Crank-Nicolson PDE Fair Pricing** — numerical PDE solver for European-style option fair values.
- **Single-Container Deployment** — everything (FastAPI, Celery, Redis, TimescaleDB, ML models) runs in one Docker container via `supervisord`.

---

## Getting Started

### 1. Clone and Configure

```bash
git clone https://github.com/NirmayKadam/MarketSentimentAnalysis2.git
cd MarketSentimentAnalysis2
cp .env.template .env
```

Edit `.env` and configure:
- **`NEWS_API_KEY`** — required for headline ingestion (free tier works).
- **`MARKET_DATA_PROVIDER`** — set to `groww` for Groww API or `nse` (default) for yfinance/NSE proxy.

### 2. Start the System

```bash
docker compose up -d
```

Open **[http://localhost:8000](http://localhost:8000)** in your browser.
