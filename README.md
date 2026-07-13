# AlphaStreams V2 — Event-Driven Options Analytics (Indian Market Focus)

A Python-based **Event-Driven Modular Monolith** combining **Real-Time NSE/BSE Options Chain Analytics** and an **Interactive Options Dashboard** to generate actionable market overviews.

Built with **FastAPI, Celery, Redis Streams, and TimescaleDB**, and a **production-grade web UI** modelled after the NSE India option chain interface.

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
- **Real-Time WebSocket Push** — live price ticks and options data streamed to the UI.
- **Crank-Nicolson PDE Fair Pricing** — numerical PDE solver for European-style option fair values.
- **Single-Container Deployment** — everything (FastAPI, Celery, Redis, and TimescaleDB) runs in one Docker container via `supervisord`.

---

## Getting Started

### 1. Clone and Configure

```bash
git clone https://github.com/NirmayKadam/MarketSentimentAnalysis2.git
cd MarketSentimentAnalysis2
cp .env.template .env
```

Edit `.env` and configure:

- **`MARKET_DATA_PROVIDER`** — set to `groww` for Groww API or `nse` (default) for yfinance/NSE proxy.

### 2. Start the System

```bash
docker compose up -d
```

Open **[http://localhost:8000](http://localhost:8000)** in your browser.
