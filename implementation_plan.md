# AlphaStreams — Technical Roadmap & Implementation Plan

This document serves as the architectural spec and technical blueprint for the project. The project strictly adheres to an **Event-Driven Architecture (EDA)**.

---

## ✅ Completed Phases

### Phase 0: Core Sentiment Pipeline
- TimescaleDB schema, NewsIngestor, Celery architecture, FinBERT scoring, SentimentRouter

### Phase 1: Market Signals Engine (Event-Driven)
- Downstream event emission, polarity math fix, SignalComposer (SMA + crossover detection), AlertDispatcher (webhook fire with Semaphore)

### Phase 2: Analytics API Expansion
- SignalsRouter, EventsRouter, asyncio loop fixes, DevOps hardening (healthchecks, .dockerignore, CPU-Torch, multi-stage builds)

### Phase 3: Derivatives & Options Analytics
- **MetricsComputer.py** — BSM pricing, PCR calculation, IV solver (Brent's method + Corrado-Miller fallback), Redis caching
- **AnomalyDetector.py** — OI surge (3×) and volume sweep (5×) detection using exponentially smoothed rolling averages
- **DerivativesAnalytics/Tasks.py** — Celery task bridging ingestion to MetricsComputer on the `derivatives` queue
- **DerivativesRouter.py** — `GET /v1/derivatives/{symbol}` returning PCR, IV surface, anomalies

### Phase 4: Live Tick Data Ingestion
- **TickIngestor.py** — Fetches live option chain from NSE India API (free, no key needed) with cookie rotation and mock fallback
- **DataIngestion/Tasks.py** — Periodic Celery tasks for news + tick ingestion cycles

---

## 🔜 Future Phases (See `research_fno_pivot.md`)

| Phase | Goal |
|:------|:-----|
| **5** | LSTM Fair-Value Model (Residual Alpha prediction) |
| **6** | Alt-Data (Twitter/Reddit/Telegram + Institutional block deals) |
| **7** | Advanced F&O Dashboard (heatmap, mispricing bars, prediction signals) |
