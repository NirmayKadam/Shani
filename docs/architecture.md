# System Architecture & Mathematical Specifications

AlphaStreams V2 is engineered as a **Modular Monolith** adhering to the principles of **Domain-Driven Design (DDD)** and **Hexagonal (Ports and Adapters) Architecture**. By enforcing strict context boundaries at the package level, the system minimizes coupling and guarantees that domains communicate exclusively via public interfaces (Ports) or asynchronous, durable event streams.

---

## 1. Architectural Philosophy & Bounded Contexts

```
               DDD + Hexagonal Flow

                    Controller
                         │
                 Input Adapter
                         │
          Input Port (Use Case)
                         │
             Application Service
                         │
           Domain (Entities, Aggregates,
           Value Objects, Domain Services)
                         │
                Output Ports (Interfaces)
                         │
               Output Adapters (JPA,
             Kafka, Email, Payment APIs)
```

### Layer Mapping Matrix

| DDD / Hexagonal Layer | Project Architecture | Codebase Location | Examples / Implementation |
|---|---|---|---|
| **Controller / Driving Adapter** | FastAPI Routers & WebSockets | `app/main.py`, `domains/*/api/` | `options.py`, `/v1/ws/{symbol}` WebSocket endpoint |
| **Input Adapter** | Request Handlers & Decoders | `domains/*/api/` | Pydantic request models & FastAPI dependency injection |
| **Input Port (Use Case)** | Service Interfaces | `domains/*/ports/interface/inbound/` | Inbound execution interfaces |
| **Application Service** | Pipeline Orchestrators | `domains/*/application/` | `BSMService`, `OptionChainIngestionService`, Celery tasks |
| **Domain Core** | Entities, Value Objects & Math | `domains/*/domain/` | `OptionChain`, `TickData`, BSM formulas, PDE grid solvers |
| **Output Ports (Interfaces)** | Abstract Data & Client Contracts | `domains/*/ports/interface/outbound/` | `IMarketPriceSourcePort`, `IOptionChainSourcePort` |
| **Output Adapters (Driven)** | External API & Storage Clients | `domains/*/infrastructure/` | `GrowwApiAdapter`, `NseApiAdapter`, `TimescaleDBRepository`, `RedisStreamBus` |


### Active Bounded Contexts

1. **Ingestion Context (`domains/ingestion`)**: Establishes connections to external financial market APIs, maintains stateful sessions, rotates HTTP cookies, parses market payloads, and publishes raw tick data structures to the messaging layer.
2. **Analytics Context (`domains/analytics`)**: The mathematical engine. Consumes ingestion event streams, executes analytical (BSM) and numerical (Crank-Nicolson PDE) option solvers, computes technical indicator formulas (RSI, MACD, Bollinger Bands, ATR, Pivots), and updates read-optimized caches.
3. **Notifications Context (`domains/notifications`)**: Real-time alert engine. Manages per-user alert rules (each rule is owned by the Supabase user who created it), evaluates symbol-level conditions (spot price above/below, ATM IV % spike) once per priced chain, fires only when a condition **crosses** from false to true, enforces the cooldown atomically in Postgres, and dispatches only through the channels chosen on the rule (WebSocket to the owner's sockets, HMAC-signed webhook, email).
4. **Historical OHLC Context (`domains/historical`)**: Historical candle persistence & data query engine. The `OhlcCandles` hypertable and repository exist, but no live candle writer feeds them yet (see Known limitations); technicals read daily history from yfinance instead.
5. **Application & Serving Context (`app/` / `frontend/`)**: Exposes REST and WebSocket gateways using FastAPI to interface with the web client. Serves static assets, provides caching mechanisms for endpoints, and manages low-latency pub/sub streaming to active web connections.
6. **Shared Kernel (`shared/`)**: Provides cross-cutting facilities including database adapters, caching client configurations, global constants, symbol validation rules, structured logging, middleware, and Celery task scheduler application context.

### Directory Taxonomy

```
MarketSentimentAnalysis2/
├── app/
│   ├── config/                        # Pydantic settings & environment configuration
│   ├── bootstrap.py                   # Domain router registration & app bootstrapping
│   └── main.py                        # FastAPI application bootstrapper & middleware
├── domains/
│   ├── ingestion/                     # Ingestion Context
│   │   ├── api/                       # REST endpoint adapters
│   │   ├── application/               # Orchestrators and Celery tasks
│   │   ├── domain/                    # Ingestion domain entities & DTOs
│   │   ├── infrastructure/            # Outbound adapters (NSE, Groww, yfinance)
│   │   ├── ports/                     # Inbound & outbound interface contracts
│   │   └── tasks/                     # Celery task definitions
│   ├── analytics/                     # Analytics Context
│   │   ├── api/                       # REST, Technicals, Pricer & WS entry adapters
│   │   ├── application/               # BSM, PDE & Technical indicator calculators
│   │   ├── domain/                    # Quantitative domain models & entities
│   │   ├── infrastructure/            # Read-model subscribers & cache repositories
│   │   ├── ports/                     # Inbound & outbound interface contracts
│   │   └── tasks/                     # Celery task definitions
│   └── notifications/                 # Notifications Context
│       ├── api/                       # Alert CRUD REST endpoints
│       ├── application/               # Alert management service
│       ├── domain/                    # Alert entities, value objects & rule matching
│       ├── infrastructure/            # Persistence, channels & subscribers
│       └── ports/                     # Inbound & outbound interface contracts
├── shared/                            # Shared Kernel
│   ├── infrastructure/                # Redis connection pools, event bus & streaming
│   ├── constants.py                   # Stream names, TTLs, and keys
│   ├── exceptions/                    # Layered exception hierarchy (API, domain, infra)
│   ├── logging/                       # Structured logging formatters & middleware
│   ├── middleware/                     # Request ID, timing, metrics & auth middleware
│   └── utils/                         # Symbol validation & timezone utilities
├── frontend/                          # Client web assets (HTML5, CSS3, Vanilla JS)
├── scripts/                           # Database migration & catalog tools
├── tests/                             # Unit, integration & e2e test suites (80+ tests)
├── docker/                            # Container configuration
│   ├── supervisord.conf               # Multi-process container configuration
│   └── start.sh                       # Container startup script
└── docker-compose.yml                 # Orchestration manifest
```

---

## 2. Process Layout & Flow Diagram

```mermaid
graph TD
    subgraph External [External Market Sources]
        NseAPI([NSE India API - Primary Webscraper / Orderbook L2])
        GrowwAPI([Groww API - Fallback Adapter])
        YfAPI([yfinance - Fallback Quote Source])
    end

    subgraph DockerContainer [Docker Container - supervisord Process Manager]
        subgraph Ingestion [Ingestion Context]
            CeleryTasks[Celery Tasks - Ingestion Worker]
            IngestionService[IngestionService - Price & Options Orchestrator]
            AdapterFactory[Adapter Factory - Pluggable Outbound Ports]
            NseAdapter[NseApiAdapter - Primary Webscraper / Cookie Session]
            GrowwAdapter[GrowwApiAdapter - Fallback Outbound Client]
        end

        subgraph OptionsPipeline [Analytics Bounded Context - Mathematical Engine]
            RawTicks["stream:options.raw_fetched"]
            OptionsSub[Options Pricing Sub - Core Subscriber Daemon]
            BSMPricer[BsmCalculatorDomainService - Analytical BSM & Greeks]
            CNPricer[Crank-Nicolson PDE Numerical Solver]
            IndicatorsEngine[TechnicalIndicatorsEngine - Vectorized RSI, MACD, BB, ATR Math]
            PricedTicks["stream:options.priced"]
        end

        subgraph NotificationsPipeline [Notifications Bounded Context]
            NotificationSub[NotificationSubscriber - Consumer Daemon]
            RuleEngine[RuleMatcherDomainService - Condition Engine]
            ChannelDispatch[Channel Adapters - WS, Webhook, Email]
        end

        subgraph HistoricalContext [Historical OHLC Bounded Context - Data Layer]
            OhlcIngestion[OHLC Candle Aggregator & Backfill Service]
            TimescaleOhlcRepo[TimescaleOhlcRepository - Hypertable Bar Persistence & Query Adapter]
        end

        subgraph Database [Historical & Hypertable Store]
            TimescaleDB[(TimescaleDB - OhlcCandles & NotificationLogs Hypertables)]
        end

        subgraph CachePubSub [Cache & Live Broadcast]
            RedisCache[(Redis Cache - Snapshot & Surface Store)]
            RedisPubSub[(Redis Pub/Sub - Ephemeral Channel Broadcast)]
        end

        subgraph Serving [API & WebSocket Serving]
            FastAPI[FastAPI Web Server - Uvicorn REST Routers]
            WSHub[WebSocket Hub - Real-time Toast & Tick Push]
        end
    end

    subgraph UserClient [Client Browser]
        WebUI[Web UI Dashboard - Options & Alert Terminal]
    end

    %% Flow lines
    NseAPI -.->|HTTP GET / Orderbook Depth| NseAdapter
    GrowwAPI -.->|HTTP POST/GET| GrowwAdapter
    YfAPI -.->|OHLC Fetch| NseAdapter

    CeleryTasks -->|Invoke via Port| IngestionService
    IngestionService --> AdapterFactory
    AdapterFactory --> NseAdapter
    AdapterFactory --> GrowwAdapter
    NseAdapter -.->|Fallback on fail| GrowwAdapter

    IngestionService ==|Publish raw option ticks|==> RawTicks
    IngestionService ==|Direct publish spot price ticks|==> RedisPubSub
    IngestionService ==|Cache price & options snapshots|==> RedisCache

    RawTicks ==|Consume raw ticks|==> OptionsSub
    RawTicks -.->|Planned: build 1m/5m candles| OhlcIngestion

    OptionsSub -->|Solve BSM & Greeks| BSMPricer
    OptionsSub -->|Evaluate PDE| CNPricer
    
    OptionsSub ==|Cache priced chain|==> RedisCache
    OptionsSub ==|Publish priced stream|==> PricedTicks
    OptionsSub ==|Broadcast option updates|==> RedisPubSub

    PricedTicks ==|Consume priced stream|==> NotificationSub
    NotificationSub -->|Match active rules| RuleEngine
    RuleEngine -->|Trigger alerts| ChannelDispatch
    ChannelDispatch -->|Publish alert toast| RedisPubSub
    ChannelDispatch -.->|Signed HTTPS POST / SMTP| External
    ChannelDispatch -->|Log alert| TimescaleDB

    OhlcIngestion -->|Bulk insert OHLC candles| TimescaleDB
    TimescaleDB -->|Query candle history| IndicatorsEngine
    IndicatorsEngine -->|Serve indicators REST| FastAPI

    RedisCache <-->|Read cache & option chains| FastAPI
    RedisPubSub ==|Push price, options & alerts|==> WSHub
    WSHub ==|WebSocket stream /ws/{symbol}|==> WebUI
```

### Ports & Adapters End-to-End Execution Sequence

```
       Control Call Flow (Top → Down)            Data Return Flow (Bottom ↑ Up)

    [ IngestionService ] (App Service)       [ IngestionService ] (App Service)
             │ (calls port)                           ▲ (returns RawTickDTO)
             ▼                                        │
    [ IOptionChainSourcePort ]               [ IOptionChainSourcePort ]
             │ (implemented by)                       ▲
             ▼                                        │
    [ GrowwApiAdapter ] (Adapter)            [ GrowwApiAdapter ] (Adapter)
             │ (HTTP request)                         ▲ (HTTP response)
             ▼                                        │
      [ Groww / NSE API ]                      [ Groww / NSE API ]
```

### Complete Sequence

```
[ Celery Task ] ──(1. trigger)──> [ IngestionService ]
                                         │
    ┌────────────────────────────────────┴────────────────────────────────────┐
    │ (2. Call Outbound Port)                                                 │ (4. Publish Outbound Port)
    ▼                                                                         ▼
[ IOptionChainSourcePort ]                                            [ IEventBusPort ]
    │ (invokes implementation)                                                │ (invokes implementation)
    ▼                                                                         ▼
[ GrowwApiAdapter ]                                                   [ RedisEventBusAdapter ]
    │                                                                         │
    ├───> HTTP fetch ───> [ External Groww API ]                              │
    │                                 │                                       │
    └───< returns DTO <───────────────┘                                       │
    │                                                                         │
    └───> returns RawTickDTO to IngestionService ─────────────────────────────┼─> Stream publish ──> [ Redis Stream ]
                                                                                                            │
                                                                                                            ▼
                                                                                             [ OptionsPricingSubscriber ]
                                                                                                            │
                                                                                                            ▼
                                                                                                    [ Redis Pub/Sub ]
                                                                                                            │
                                                                                                            ▼
                                                                                                   [ WebSocket Gateway ]
```

1. **Trigger (Driving Input):** while a symbol has WebSocket viewers, the API's polling loop dispatches Celery task `ingestion.fetch_and_publish_options` every 15 s (prices every 5 s). Every uvicorn worker runs the loop, so each dispatch first claims a Redis slot (`SET poll:slot:{kind}:{symbol} NX PX`); exactly one worker polls a symbol per interval.
2. **Fetch (Outbound Port -> Outbound Adapter):** the task calls `IOptionChainSourcePort.fetch_option_chain(symbol)` on the adapter from `get_market_data_adapter`, which is shared per event loop so HTTP sessions, NSE cookies and the Groww token are reused.
3. **Skip unchanged chains:** the task hashes the chain's market fields. If the hash matches the last one (outside market hours, or between exchange updates), it refreshes the raw-chain cache and stops: no TickData insert, no re-pricing. The hash key expires at half the priced-chain TTL, so the read model never goes stale.
4. **Persist and publish:** every expiry goes to TimescaleDB (`COPY`), the raw chain to `market:options:{symbol}`, and the nearest expiry's near-the-money strikes to `stream:options.raw_fetched` (length-bounded `XADD`).
5. **Price (Driven Consumer):** `OptionsPricingSubscriber` reads the stream through a consumer group, prices the chain (batched Crank-Nicolson plus vectorised BSM in a process pool), caches it in `market:options:priced:{symbol}`, publishes `stream:options.priced`, and sends a small `{symbol, last_updated}` message on Pub/Sub. The WebSocket gateway relays it and the browser refetches the chain.

### Real-Time Live Data WebSocket & Pub/Sub Fan-Out Flow

```mermaid
sequenceDiagram
    participant ExternalAPI as External Market APIs
    participant Ingestion as Ingestion Domain
    participant RedisStreams as Redis Streams / Cache
    participant PDE as Analytics Domain (PDE/BSM)
    participant PubSub as Redis Pub/Sub
    participant EventRouter as FastAPI WS Gateway
    participant Frontend as Frontend (app.js)

    %% 1. Direct Spot Price Flow (Ingestion -> Pub/Sub -> WS -> Frontend)
    rect rgb(240, 248, 255)
        note over ExternalAPI, Frontend: 1. Spot Price Tick Flow (Direct Ingestion Push)
        ExternalAPI->>Ingestion: Fetch Live Spot Price
        Ingestion->>RedisStreams: Cache snapshot (market:price:{symbol})
        Ingestion->>PubSub: Publish market.price_updated.{symbol}
        PubSub->>EventRouter: Global Listener (psubscribe)
        EventRouter->>Frontend: Push WS {"type": "price", "data": {...}}
        Frontend->>Frontend: Update spot & re-solve client BSM/Greeks
    end

    %% 2. Processed Options Pricing Flow (Ingestion -> Stream -> Analytics -> Pub/Sub -> WS -> Frontend)
    rect rgb(255, 248, 240)
        note over ExternalAPI, Frontend: 2. Processed Option Chain Flow (Async Analytics Pipeline)
        ExternalAPI->>Ingestion: Fetch Option Chain Raw Ticks
        Ingestion->>RedisStreams: Push stream:options.raw_fetched
        PDE->>RedisStreams: Read stream:options.raw_fetched
        PDE->>PDE: Solve Crank-Nicolson PDE & Analytical BSM
        PDE->>RedisStreams: Cache priced chain (market:options:priced:{symbol})
        PDE->>PubSub: Publish market.options_updated.{symbol}
        PubSub->>EventRouter: Global Listener (psubscribe)
        EventRouter->>Frontend: Push WS {"type": "options", "data": {...}}
        Frontend->>RedisStreams: GET /v1/pricer/ticker/{symbol} (Render Grid)
    end
```

---

## 3. Ingestion Context & Pluggable Data Adapters

Data ingestion operates via an interface-driven architecture, decoupling pipeline execution from concrete API providers through `IMarketPriceSourcePort` and `IOptionChainSourcePort`.

### Adapter Factory & Session Management
* **`GrowwApiAdapter`**: Primary live option chain and quote retrieval. The daily access token is shared across processes in Redis (`groww:access_token`) until one minute before it expires; the expiry list is cached per IST trading day; dividend yield is cached in Redis.
* **`NseApiAdapter`**: Connects to NSE India API. Serves as primary driver under `MARKET_DATA_PROVIDER="nse"` or fallback when Groww credentials expire. IV is normalised to a decimal (both adapters emit 0.142, not 14.2). yfinance `ticker.info` (dividend yield, currency) is cached per process for 24 h; yfinance reports `dividendYield` in percent, so the yield is derived from `dividendRate / price`.
* **Per-loop singletons**: `get_market_data_adapter()` returns one adapter per event loop. Callers must not close it.
* **Single-flight cache misses**: when `/v1/pricer/ticker/{symbol}` misses the cache, the first request takes a Redis lock (`pricer:fetching:{symbol}`) and fetches; concurrent requests wait for its cached result instead of all hitting the market sources. A live fetch has an overall 25 s deadline.
* **Session Cookie Rotation**: Performs initial warm-up sequence (`https://www.nseindia.com`) and programmatically refreshes session cookies every 10 minutes (600s).
* **Tiered Market Fallback**:
  1. Redis Cache check.
  2. Primary Adapter (Groww API / `yfinance`).
  3. Secondary NSE Scraper.
  4. **Fail-Fast Error Policy (HTTP 503)**: Purged synthetic mock generators. Returns clean `503 Service Unavailable` if external streams fail.

---

## 4. Option Pricing & Mathematical Solvers

### Analytical Model: Black-Scholes-Merton (BSM)

Closed-form formulation with continuous dividend yield:

$$d_1 = \frac{\ln\left(\frac{S_0}{K}\right) + \left(r - q + \frac{\sigma^2}{2}\right)T}{\sigma\sqrt{T}}$$
$$d_2 = d_1 - \sigma\sqrt{T}$$

* **Call Theoretical Price ($C_{BSM}$):**
  $$C_{BSM} = S_0 e^{-q T} N(d_1) - K e^{-r T} N(d_2)$$
* **Put Theoretical Price ($P_{BSM}$):**
  $$P_{BSM} = K e^{-r T} N(-d_2) - S_0 e^{-q T} N(-d_1)$$

#### Dynamic Greeks Formulations
* **Delta ($\Delta$):** $\Delta_{Call} = e^{-q T} N(d_1), \quad \Delta_{Put} = -e^{-q T} N(-d_1)$
* **Gamma ($\Gamma$):** $\Gamma = \frac{e^{-q T} n(d_1)}{S_0 \sigma \sqrt{T}} \quad \text{where } n(x) = \frac{1}{\sqrt{2\pi}} e^{-\frac{x^2}{2}}$
* **Vega ($\nu$):** $\nu = \frac{S_0 e^{-q T} \sqrt{T} n(d_1)}{100}$
* **Theta ($\Theta$):**
  $$\Theta_{Call} = \frac{- \frac{S_0 e^{-q T} n(d_1) \sigma}{2 \sqrt{T}} + q S_0 e^{-q T} N(d_1) - r K e^{-r T} N(d_2)}{365}$$
  $$\Theta_{Put} = \frac{- \frac{S_0 e^{-q T} n(d_1) \sigma}{2 \sqrt{T}} - q S_0 e^{-q T} N(-d_1) + r K e^{-r T} N(-d_2)}{365}$$
* **Rho ($\rho$):** $\rho_{Call} = \frac{K T e^{-r T} N(d_2)}{100}, \quad \rho_{Put} = \frac{-K T e^{-r T} N(-d_2)}{100}$

---

### Numerical Solver: Crank-Nicolson PDE Scheme

Solves the Black-Scholes partial differential equation:

$$\frac{\partial V}{\partial t} + \frac{1}{2}\sigma^2 S^2 \frac{\partial^2 V}{\partial S^2} + (r - q) S \frac{\partial V}{\partial S} - r V = 0$$

#### Grid Discretization
1. **Stock Price Domain**: $S \in [\min(S_0, K)\,e^{-w},\ \max(S_0, K)\,e^{w}]$ with $w = 4\sigma\sqrt{T}$: four standard deviations of the log-price at expiry beyond both spot and strike, with $M$ uniform steps.
2. **Temporal Domain**: $\tau \in [0, T]$ with $N$ steps ($dt = T/N$).
3. **Stability**: Crank-Nicolson is unconditionally stable for this equation, so no CFL check is needed. The first 2 steps are replaced by 4 fully implicit half-steps (Rannacher start-up) to damp oscillations from the payoff's kink at the strike.
4. **Boundaries**: call top edge $S_{max} e^{-q\tau} - K e^{-r\tau}$, put bottom edge $K e^{-r\tau} - S_{min} e^{-q\tau}$, zero on the other edge.

#### Linear System Construction
Discretized implicit/explicit formulation (unknown new level on the left):

$$- \alpha_i V_{i-1}^{new} + (1 + \beta_i) V_i^{new} - \gamma_i V_{i+1}^{new} = \alpha_i V_{i-1}^{old} + (1 - \beta_i) V_i^{old} + \gamma_i V_{i+1}^{old}$$

Where, with $D_i = \frac{\sigma^2 S_i^2}{2\,dS^2}$ and $R_i = \frac{(r - q) S_i}{2\,dS}$:
$$\alpha_i = \frac{dt}{2} \left( D_i - R_i \right), \qquad \beta_i = \frac{dt}{2} \left( 2D_i + r \right), \qquad \gamma_i = \frac{dt}{2} \left( D_i + R_i \right)$$

Formulated as tridiagonal system: $\mathbf{A} \mathbf{V}^{new} = \mathbf{B} \mathbf{V}^{old} + \text{boundary}$.

Accuracy against closed-form BSM over strikes ±10%, 1-60 days, 10-40% IV: worst error ₹0.19, mean ₹0.022 (was ₹21.20 and ₹0.94 on the old $[0, 3K]$ grid without dividends or Rannacher).

#### SciPy Sparse Matrix LU Optimization
Matrix $\mathbf{A}$ is static and pre-factorized using SuperLU direct solver (`scipy.sparse.linalg.splu`) outside the temporal loop. Resolves backward steps in linear $O(M)$ time via `A_solver.solve(rhs)`.

#### Batched Chain Pricing
`price_chain_cn` stacks a chunk of contracts (each with its own grid and σ) as blocks of one block-diagonal tridiagonal system, so each time step is one `B.dot` and one SuperLU solve for all of them. The subscriber splits a chain into one chunk per worker of a spawn-based `ProcessPoolExecutor` (`PRICING_WORKERS`). Measured end to end on a 100-contract chain: 527 contracts/s with 1 worker, 975 with 2, 1,291 with 4. See [SuperLU_PDE_Explanation.md](SuperLU_PDE_Explanation.md) for the full walkthrough.

---

## 5. Storage & Event Streaming Infrastructure

### TimescaleDB Hypertables & Relational Persistence
* **`OhlcCandles` Hypertable**: Partitioned on `timestamp` column. Auto-retention policy drops 1m/5m/1d candles older than 90 days.
* **`NotificationLogs` Hypertable**: Partitioned on `timestamp` column. Auto-retention policy purges triggered alert log entries older than 14 days.
* **`TickData` Hypertable**: Partitioned on `timestamp` column. Automatic data retention drops raw tick chunks older than 90 days.

| Table Name | Partitioning | Primary Columns | Purpose & Retention |
|---|---|---|---|
| `OhlcCandles` | Hypertable | `symbol`, `timestamp`, `timeframe`, `open`, `high`, `low`, `close`, `volume` | Historical 1m/5m/1d candles (90-day retention). |
| `NotificationLogs` | Hypertable | `id`, `rule_id`, `symbol`, `condition_type`, `triggered_value`, `threshold`, `message`, `status`, `timestamp` | Triggered alert audit log (14-day retention). |
| `AlertRules` | Relational | `id`, `user_id`, `symbol`, `condition_type`, `threshold`, `channels`, `cooldown_seconds`, `last_condition_met`, `last_triggered_at`, `webhook_secret`, `is_active` | Per-user alert rules, crossing state & destinations. |
| `TickData` | Hypertable | `Timestamp`, `Symbol`, `StrikePrice`, `LastPrice`, `Volume`, `ImpliedVolatility` | Raw tick database (90-day retention). |
| `DomainEvents` | Relational | `EventId` (UUID), `EventType`, `Payload` (JSONB), `OccurredAt` | Cross-domain event audit log. |

### Redis Streams Messaging Architecture
1. `stream:options.raw_fetched`: Ingestion worker pushes the nearest expiry's chain. Read by consumer group `cg:options_pricing`.
2. `stream:options.priced`: `OptionsPricingSubscriber` writes the priced chain plus `spot_price`, `atm_iv_pct`, `expiry`. Read by consumer group `cg:alert_evaluation`.
3. Each stream has a dead-letter stream (`stream:dlq:options.raw_fetched`, `stream:dlq:options.priced`). Consumers (`run_durable_consumer`) acknowledge a message only after handling it, retry failures (2 retries for pricing, 5 for alerts), then move the message to the DLQ, and periodically reclaim messages left pending by a crashed consumer (`XAUTOCLAIM`). A new group starts at `$`, so history is not replayed. Every `XADD` is length-bounded (`MAXLEN ~ 10000`). `scripts/read_dlq.py <stream>` inspects a DLQ.
4. `market.options_updated.{symbol}` / `market.price_updated.{symbol}`: Ephemeral Pub/Sub channels mirror updates to the WebSocket hub (`/v1/ws/{symbol}`). The options message carries only `{symbol, last_updated}`; the browser refetches the chain.
5. `alerts.dispatched.{symbol}`: Ephemeral Pub/Sub channel for alerts. The payload carries `user_id`, and the hub forwards it only to sockets authenticated as that user.

### Security
* **Authentication**: Supabase JWTs are verified with PyJWT (ES256/RS256 through the project's JWKS, or HS256 with `SUPABASE_JWT_SECRET`), audience `authenticated`. Alert endpoints require a valid token; other users' rules return 404.
* **WebSockets**: market data is public. A client sends `{"action": "auth", "token": ...}` to receive its own alerts. Connection and symbol caps apply.
* **Webhooks**: HTTPS only, destination resolved and rejected if private, loopback or link-local (SSRF guard). Each rule has its own secret, returned once on creation, and payloads are signed with HMAC-SHA256.
* **Container**: application processes run as a non-root user; the database role is not a superuser.

### Known Limitations
* `VolatilitySurface` exists in the analytics domain but is not wired into the live pipeline.
* No live OHLC candle writer feeds `OhlcCandles`; technicals use yfinance daily history (cached for 1 h).
* No Prometheus metrics endpoint.
* Some modules still import across bounded contexts (e.g. the analytics API uses ingestion adapters), and the middleware layers are not merged.

---

## 6. Frontend SPA & Client Math Engine

* **SPA Architecture**: Dark glassmorphic trading terminal layout in vanilla HTML5/CSS3/JS.
* **Client BSM Simulation**: Runs Hastings' cumulative normal distribution approximation ($N(x)$) inside browser JS for zero-latency slider calculations:

```javascript
function normalCDF(x) {
    const b1 = 0.319381530, b2 = -0.356563782, b3 = 1.781477937, 
          b4 = -1.821255978, b5 = 1.330274429, p = 0.2316419;
    const t = 1.0 / (1.0 + p * Math.abs(x));
    const poly = t * (b1 + t * (b2 + t * (b3 + t * (b4 + t * b5))));
    const cdf = 1.0 - (1.0 / Math.sqrt(2 * Math.PI)) * Math.exp(-0.5 * x * x) * poly;
    return x >= 0 ? cdf : 1.0 - cdf;
}
```

---

## 7. Regulatory Compliance & Disclaimers

### SEBI Risk Disclosure
> "9 out of 10 individual traders in equity derivatives segment incurred net losses, averaging ₹50,000 loss per year, with an additional 28% in transaction costs."

### Investment Disclaimer
All theoretical pricing metrics and PDE outputs are strictly for research and educational purposes. The platform operators are not registered SEBI Investment Advisers (IA) or Research Analysts (RA).
