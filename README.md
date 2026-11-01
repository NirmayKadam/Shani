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
- **Technical Indicators** — RSI, MACD, Bollinger Bands, ATR, EMA/SMA crossovers and Pivot Points from daily history, with a composite bullish/bearish signal.
- **Client-Side BSM Calculator** — real-time Black-Scholes-Merton pricing, full Greeks (Δ, Γ, ν, θ, ρ), and theoretical edge overlays.
- **User Profile Management** — Supabase Auth integration with glassmorphic profile modal for real-time metadata updates.
- **Dynamic Instrument Search** — debounced autocomplete search across 2,000+ NSE equities and indices via a live instrument catalog.
- **Real-Time WebSocket Push** — live price ticks, option chain updates and per-user alerts.
- **Crank-Nicolson PDE Fair Pricing** — numerical PDE solver for European options with dividend yield, an adaptive grid and Rannacher start-up; within ₹0.19 of closed-form BSM across the chain. Whole chains are priced in one batched sparse solve across a process pool (about 1,300 contracts/s on 4 workers). See [the walkthrough](docs/SuperLU_PDE_Explanation.md).
- **Real-Time Alert Rules & Notifications** — per-user rules on spot price and ATM IV that fire when the condition crosses, with atomic cooldowns, delivered by WebSocket, HMAC-signed webhook or email.
- **Durable Event Pipeline** — Redis Streams consumer groups with acknowledgement, retries, dead-letter streams and reclaim of stalled messages.
- **Single-Container Deployment** — everything (FastAPI, Celery, Redis, and TimescaleDB) runs in one Docker container via `supervisord`.

---

## Getting Started

### 1. Clone and Configure

```bash
git clone https://github.com/NirmayKadam/Shani.git
cd Shani
cp .env.example .env
```

Edit `.env` and configure:

- **`MARKET_DATA_PROVIDER`** — set to `groww` for Groww API or `nse` (default) for yfinance/NSE proxy.
- **`supabaseUrl` / `supabaseKey`** — your Supabase project URL and **anon** key (served to the browser by `/config`; never put the service-role key here). Alert endpoints verify Supabase access tokens against the project's JWKS; set `SUPABASE_JWT_SECRET` only for legacy HS256 projects.
- **`PRICING_WORKERS`** — processes in the pricing pool (blank = CPU count − 1).
- **`SMTP_*`** — required only for email alerts.

### Running the tests

```bash
python -m pytest
```

Unit tests run by default; `integration` and `live` tests are opt-in (`-m integration`).

### 2. Start the System

```bash
docker compose up -d
```

Open **[http://localhost:8000](http://localhost:8000)** in your browser.
