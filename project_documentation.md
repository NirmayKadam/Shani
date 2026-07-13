# AlphaStreams V2: Market Sentiment & Option Chain Analytics Engine
## Comprehensive System & Mathematical Architecture Documentation

This document provides a rigorous, professional-grade technical specification of the architecture, data schemas, mathematical formulations, numerical methods, deep learning pipelines, and containerized deployment lifecycle of **AlphaStreams V2** (MarketSentimentAnalysis2). It serves as the primary system reference for engineering, operations, and quantitative development.

---

## 1. Architectural Philosophy & Bounded Contexts

AlphaStreams V2 is engineered as a **Modular Monolith** adhering to the principles of **Domain-Driven Design (DDD)** and **Hexagonal (Ports and Adapters) Architecture**. By enforcing strict context boundaries at the package level, the system minimizes coupling and guarantees that domains communicate exclusively via public interfaces (Ports) or asynchronous, durable event streams.

```
                                  +------------------------------------+
                                  |         API & UI Adapter           |
                                  |   (FastAPI Routers, WebSockets)    |
                                  +-----------------+------------------+
                                                    |
                                                    v
                                  +-----------------+------------------+
                                  |          Domain Ports              |
                                  |   (IMarketPriceSourcePort, etc.)   |
                                  +-----------------+------------------+
                                                    |
                                     +--------------+--------------+
                                     |                             |
                                     v                             v
                       +-------------+-------------+ +-------------+-------------+
                       |     Ingestion Domain      | |     Analytics Domain      |
                       | (Data Retrieval, Polling) | |   (PDE, BSM, ML, NLP)     |
                       +-------------+-------------+ +-------------+-------------+
                                     |                             |
                                     +--------------+--------------+
                                                    |
                                                    v
                                  +-----------------+------------------+
                                  |      Shared Infrastructure         |
                                  | (TimescaleDB, Redis, Event Bus)   |
                                  +------------------------------------+
```

### Active Bounded Contexts

1. **Ingestion Context (`domains/ingestion`)**: Responsible for establishing connections to external financial market APIs, maintaining stateful sessions, managing HTTP cookie rotation, parsing market-specific payloads, and publishing validated raw data structures to the messaging layer.
2. **Analytics Context (`domains/analytics`)**: The mathematical and forecasting engine. It consumes ingestion event streams, executes analytical and numerical options solvers (BSM & Crank-Nicolson PDE), runs PyTorch-based volatility predictions, evaluates headline sentiments using transformer models, and updates read-optimized caches.
3. **Application & API Context (`app/` / `static/`)**: Exposes REST and WebSocket gateways using FastAPI to interface with the web client. It serves static assets, provides caching mechanisms for endpoints, and manages low-latency pub/sub streaming to active web connections.
4. **Shared Infrastructure (`shared/`)**: Provides cross-cutting facilities including database adapters, caching client configuration, global constants, symbol validation rules, and the Celery task scheduler application context.

### Directory Structure and Component Taxonomy

```
MarketSentimentAnalysis2/
├── app/
│   ├── api/                           # Entry point adapters (routers)
│   ├── config.py                      # Pydantic configuration schemas
│   └── main.py                        # FastAPI application bootstrapper
├── domains/
│   ├── ingestion/                     # Ingestion Context
│   │   ├── api/                       # REST endpoint adapters
│   │   ├── application/               # Orchestrators and Celery tasks
│   │   ├── dto/                       # Data Transfer Objects (DTOs)
│   │   ├── domain/                    # Ingestion domain entities
│   │   └── infrastructure/            # Outbound adapters (NSE, Groww, NewsAPI)
│   └── analytics/                     # Analytics Context
│       ├── api/                       # REST and WebSocket entry adapters
│       ├── application/               # Pricing solvers and ML estimators
│       ├── domain/                    # Quantitative domain models
│       └── infrastructure/            # Database and read-model subscribers
├── shared/                            # Shared Kernel
│   ├── infrastructure/                # Redis and Database connection pools
│   ├── constants.py                   # Stream names, TTLs, and keys
│   └── utils/                         # Symbol and timezone utilities
├── static/                            # Client assets (HTML, CSS, JS)
├── scripts/                           # Schema migrations and ML training scripts
├── tests/                             # Unit and integration test suites
├── supervisord.conf                   # Multi-process configuration
├── start.sh                           # Container startup script
└── docker-compose.yml                 # Orchestration manifest
```

---

## 2. Ingestion Context & Pluggable Data Adapters

Data ingestion operates via an interface-driven architecture, decoupling the pipeline execution from concrete API providers. The outbound adapters implement the interfaces defined by `IMarketPriceSourcePort` and `IOptionChainSourcePort`.

### Pluggable Adapter Factory

The `get_market_data_adapter` factory dynamically instantiates the outbound adapter according to the `MARKET_DATA_PROVIDER` environment variable:
*   **Groww API Adapter (`GrowwApiAdapter`)**: Implements primary live options and quote retrieval using the Groww API. It handles token generation dynamically and queries `/v1/live-data/quote` for market quotes, caching auxiliary information (like dividend yield) in Redis.
*   **NSE India API Adapter (`NseApiAdapter`)**: Connects to the National Stock Exchange of India API. It serves as the primary driver under the `"nse"` setting and is the automatic fallback for the Groww adapter if API access credentials become invalid.

```
                              +------------------------+
                              |     AdapterFactory     |
                              +-----------+------------+
                                          |
                        +-----------------+-----------------+
                        | (MarketDataProvider == "groww")   | (MarketDataProvider == "nse")
                        v                                   v
             +----------+----------+             +----------+----------+
             |   GrowwApiAdapter   |             |    NseApiAdapter    |
             +----------+----------+             +---------------------+
                        | (Fallback)
                        v
             +----------+----------+
             |    NseApiAdapter    |
             +---------------------+
```

### NSE API Session Management and Cookie Rotation

To prevent service denials due to rate limits or invalid sessions, `NseApiAdapter` executes stateful session management:
1.  **Warm-up Sequence**: The adapter performs an initial `GET` request to `https://www.nseindia.com` to capture essential session cookies.
2.  **Referer Initialization**: It immediately accesses the main options chain landing page at `https://www.nseindia.com/option-chain?symbol={SYMBOL}` to establish referer headers.
3.  **Cookie Lifetime Monitoring**: Cookies are audited and programmatically refreshed every 10 minutes (600 seconds) to ensure continuous, uninterrupted API connectivity.
4.  **Event Loop Safety**: To avoid cross-thread event loop conflicts within the Celery worker threads, the underlying `aiohttp.ClientSession` singleton is automatically validated against the active event loop (`asyncio.get_running_loop()`). If a boundary crossing is detected, the adapter transparently closes and re-initializes the session.

### Tiered Market Data Fallback Strategy

To ensure zero downtime and strict financial accuracy without outputting misleading data, `NseApiAdapter` and `AdapterFactory` enforce a hierarchical real-time market data fallback chain:
1.  **Redis In-Memory Cache**: Checked first for pre-fetched option chain grids and underlying spot quotes.
2.  **Primary Outbound Adapters (Groww API / Yahoo Finance `yfinance`)**: Queries real-time tick feeds and underlying asset prices.
3.  **NSE India Web Scraper**: Acts as the secondary real-time fallback by scraping options tables directly from NSE India.
4.  **Fail-Fast Error Policy (HTTP 503)**: Synthetic deterministic mock generators have been completely purged from the analytics pricer engine. If market data cannot be retrieved across all providers (e.g. during total network failure or provider outages), the API raises an explicit `HTTP 503 Service Unavailable` error, guaranteeing that no false or synthetic financial information reaches quantitative models or end users.

---

## 3. Persistent Storage & Event Streaming Infrastructure

The infrastructure layer guarantees time-series data storage efficiency and handles inter-domain message delivery using durable and ephemeral transport channels.

### TimescaleDB (PostgreSQL 15 Engine)

High-frequency market snapshot storage is optimized using TimescaleDB **hypertables**:
*   **`TickData` Table**: Configured as a hypertable partitioned along the `Timestamp` column with a 1-day interval (`chunk_time_interval => INTERVAL '1 day'`).
*   **Retention Policy**: An automatic data retention policy drops chunks older than 7 days, capping storage footprint.
*   **Relational Database Schema**:

| Table Name | Partitioning Style | Primary Columns / Types | Purpose |
|---|---|---|---|
| `TickData` | Hypertable (Time-series) | `Timestamp` (TIMESTAMPTZ), `Symbol` (VARCHAR), `StrikePrice` (NUMERIC), `OptionType` (VARCHAR(2)), `LastPrice` (NUMERIC), `OpenInterest` (BIGINT), `Volume` (BIGINT), `ImpliedVolatility` (NUMERIC) | Options tick record database. |
| `SentimentScores` | Standard Relational | `id` (UUID), `Timestamp` (TIMESTAMPTZ), `Symbol` (VARCHAR), `Headline` (TEXT), `SentimentLabel` (VARCHAR), `SentimentScore` (NUMERIC), `SourceUrl` (TEXT) | NLP FinBERT model output repository. |
| `DetectedEvents` | Standard Relational | `id` (UUID), `Timestamp` (TIMESTAMPTZ), `EventType` (VARCHAR), `Payload` (JSONB) | Logs structural anomalies or macro events. |
| `AlertRules` | Standard Relational | `id` (UUID), `Symbol` (VARCHAR), `ConditionType` (VARCHAR), `Threshold` (NUMERIC), `WebhookUrl` (TEXT) | Stores user-defined notification triggers. |
| `DomainEvents` | Standard Relational | `id` (UUID), `EventName` (VARCHAR), `OccurredAt` (TIMESTAMPTZ), `Payload` (JSONB) | Audit trail of major domain events. |

### Redis Streams Messaging Architecture

The system uses **Redis Streams** for asynchronous cross-domain communication, achieving low latency while preserving message delivery guarantees.

```
+------------------+     stream:options.raw_fetched     +--------------------+     stream:options.priced     +----------------------+
| Ingestion Task   | ---------------------------------> | Options Pricing    | -----------------------------> | Read-Model Updater / |
| (Celery / Ingest)|                                    | Subscriber (PDE)   |                                | FastAPI App WS Hub   |
+------------------+                                    +--------------------+                                +----------------------+
                                                                                                                         |
                                                                                                                         | (Pub/Sub Broadcast)
                                                                                                                         v
                                                                                                              +----------------------+
                                                                                                              |  channel:options:    |
                                                                                                              |  updated:{SYMBOL}    |
                                                                                                              +----------------------+
```

1.  **Durable Processing Pipeline**:
    *   **Raw Options Streaming**: Ingestion services publish raw options data blocks directly into the `stream:options.raw_fetched` stream.
    *   **Pricer Processing**: The `OptionsPricingSubscriber` daemon consumes raw ticks, runs Black-Scholes-Merton (BSM) and Crank-Nicolson solvers, and pushes structured results to the `stream:options.priced` stream.
    *   **Cache Synchronization**: The `ReadModelUpdater` process reads priced events and updates Redis keys for immediate API consumption.
2.  **Durable Stream Definitions**:
    *   `stream:headlines.fetched`: Raw text headlines parsed by news adapters.
    *   `stream:sentiment.scored`: Enriches headlines with target sentiments.
    *   `stream:options.raw_fetched`: Raw option chain ticks.
    *   `stream:options.priced`: Volatility and PDE fair price calculations.
3.  **Dead-Letter Queue (DLQ) Strategy**:
    If a consumer fails to process a stream event (due to JSON syntax issues, DB connection loss, etc.) after 3 retries, the event is acknowledged in the main stream and forwarded to a specialized dead-letter queue (e.g., `stream:dlq:ingestion_to_nlp` or `stream:dlq:refresh_request`) via the `stream_bus.retry_or_dead_letter(...)` interface to prevent consumer group starvation and PEL leakage.
4.  **Consumer Loop Fault-Tolerance**:
    The raw option pricing subscriber (`options_subscriber.py`) wraps event processing within active try-except guards. This protects the primary daemon process against crashes caused by malformed ticks or downstream database write exceptions.
5.  **Ephemeral Pub/Sub Mirroring**:
    To feed front-end clients via WebSockets, critical processed data is mirrored to Redis Pub/Sub channels (e.g., `channel:options:updated:{SYMBOL}`). Front-end clients subscribe to these channels to receive immediate visual updates.

---

## 4. Option Pricing & Mathematical Solvers

The analytical engine evaluates theoretical option prices and sensitivity parameters using both analytical (closed-form) and numerical (discretized grid) methodologies.

### 1. Analytical Solver: Black-Scholes-Merton (BSM) Model

For standard pricing, the engine implements the closed-form BSM formulation, modified to support a continuous dividend yield:

$$d_1 = \frac{\ln\left(\frac{S_0}{K}\right) + \left(r - q + \frac{\sigma^2}{2}\right)T}{\sigma\sqrt{T}}$$
$$d_2 = d_1 - \sigma\sqrt{T}$$

*   **Call Theoretical Price ($C_{BSM}$):**
    $$C_{BSM} = S_0 e^{-q T} N(d_1) - K e^{-r T} N(d_2)$$
*   **Put Theoretical Price ($P_{BSM}$):**
    $$P_{BSM} = K e^{-r T} N(-d_2) - S_0 e^{-q T} N(-d_1)$$

Where:
*   $S_0$ = Asset spot price, $K$ = Option strike price, $T$ = Annualized time to expiration ($T_{days} / 365$).
*   $r$ = Annual risk-free interest rate, $q$ = Annual dividend yield.
*   $\sigma$ = Implied volatility, $N(\cdot)$ = Cumulative standard normal distribution function.

#### Greeks Computation
Greeks are calculated dynamically for the ATM indicator dashboard card:
*   **Delta ($\Delta$):**
    $$\Delta_{Call} = e^{-q T} N(d_1), \quad \Delta_{Put} = -e^{-q T} N(-d_1)$$
*   **Gamma ($\Gamma$):**
    $$\Gamma = \frac{e^{-q T} n(d_1)}{S_0 \sigma \sqrt{T}} \quad \text{where } n(x) = \frac{1}{\sqrt{2\pi}} e^{-\frac{x^2}{2}}$$
*   **Vega ($\nu$):**
    $$\nu = \frac{S_0 e^{-q T} \sqrt{T} n(d_1)}{100}$$
*   **Theta ($\Theta$):**
    $$\Theta_{Call} = \frac{- \frac{S_0 e^{-q T} n(d_1) \sigma}{2 \sqrt{T}} + q S_0 e^{-q T} N(d_1) - r K e^{-r T} N(d_2)}{365}$$
    $$\Theta_{Put} = \frac{- \frac{S_0 e^{-q T} n(d_1) \sigma}{2 \sqrt{T}} - q S_0 e^{-q T} N(-d_1) + r K e^{-r T} N(-d_2)}{365}$$
*   **Rho ($\rho$):**
    $$\rho_{Call} = \frac{K T e^{-r T} N(d_2)}{100}, \quad \rho_{Put} = \frac{-K T e^{-r T} N(-d_2)}{100}$$

---

### 2. Numerical Solver: Crank-Nicolson PDE Scheme

For advanced pricing, the engine solves the Black-Scholes partial differential equation:

$$\frac{\partial V}{\partial t} + \frac{1}{2}\sigma^2 S^2 \frac{\partial^2 V}{\partial S^2} + r S \frac{\partial V}{\partial S} - r V = 0$$

#### Grid Discretization
1.  **Stock Price Domain**: Discretized on $S \in [0, S_{max}]$, where $S_{max} = \max(3K, 2.5S_0)$ to minimize boundary error. The grid size is defined by $M$ steps: $dS = S_{max}/M$, creating price nodes $S_i = i \cdot dS$ for $i \in [0, M]$.
2.  **Temporal Domain**: Discretized on $t \in [0, T]$ with $N$ steps: $dt = T/N$, creating temporal nodes $t_j = j \cdot dt$ for $j \in [0, N]$.
3.  **CFL Stability Check**: To ensure convergence when integrating the explicit component of the Crank-Nicolson scheme, the system audits the grid configuration. If the time step violates the stability criteria:
    $$dt > \frac{0.9}{\sigma^2 M^2} S_{max}^2$$
    the system automatically increases $N$ to reduce the time step size.

#### Linear System Construction
The Crank-Nicolson scheme approximates the spatial operator using an average of implicit and explicit steps:

$$- \alpha_i V_{i-1}^{j} + (1 + \beta_i) V_i^{j} - \gamma_i V_{i+1}^{j} = \alpha_i V_{i-1}^{j+1} + (1 - \beta_i) V_i^{j+1} + \gamma_i V_{i+1}^{j+1}$$

Using the coefficients defined in the code implementation:
$$\alpha_i = -\frac{1}{4} dt \left( \sigma^2 i^2 - r i \right)$$
$$\beta_i = \frac{1}{2} dt \left( \sigma^2 i^2 + r \right)$$
$$\gamma_i = -\frac{1}{4} dt \left( \sigma^2 i^2 + r i \right)$$

This is formulated as the tridiagonal matrix equation solved backward in time:
$$\mathbf{A} \mathbf{V}^j = \mathbf{B} \mathbf{V}^{j+1}$$

Where:
*   $\mathbf{A}$ is the LHS tridiagonal matrix with main diagonal elements $(1 - \beta_i)$ and off-diagonals $-\alpha_i$ (below) and $-\gamma_i$ (above).
*   $\mathbf{B}$ is the RHS tridiagonal matrix with main diagonal elements $(1 + \beta_i)$ and off-diagonals $\alpha_i$ (below) and $\gamma_i$ (above).

#### Boundary Conditions
*   **Call Boundary Conditions**:
    *   Lower bound ($S=0$): $V_0^j = 0$
    *   Upper bound ($S=S_{max}$): $V_M^j = S_{max} - K e^{-r (T - t_j)}$
    *   RHS correction at node $M-1$: $\text{rhs}[-1] \mathrel{+}= \gamma_{M-1} (V_M^j + V_M^{j+1})$
*   **Put Boundary Conditions**:
    *   Lower bound ($S=0$): $V_0^j = K e^{-r (T - t_j)}$
    *   Upper bound ($S=S_{max}$): $V_M^j = 0$
    *   RHS correction at node $1$: $\text{rhs}[0] \mathrel{+}= \alpha_1 (V_0^j + V_0^{j+1})$

#### SciPy Sparse Solver Integration
Because $\mathbf{A}$ is a static, time-invariant tridiagonal matrix, the engine optimizes the solution by pre-factorizing it using the SuperLU direct solver (`scipy.sparse.linalg.splu`) outside the temporal loop. During each backward step, the pre-factorized solver resolves the system in linear $O(M)$ time using `A_solver.solve(rhs)`. This bypasses the overhead of recalculating sparse LU decompositions inside the loop (shifting execution complexity from $O(N \cdot \text{factorization})$ to a single factorization and $N$ back-solves), and the final value is obtained via linear interpolation at the spot price $S_0$.

---

## 5. Machine Learning & Volatility Prediction

The analytics context hosts a pre-trained PyTorch network predicting volatility trend transitions over a 5-day horizon, classifying them into `VOL_CRUSH`, `NEUTRAL`, or `VOL_EXPAND`.

```
                                     [Input Sequence]
                                     /      |       \
                                    /       |        \
                              Daily(21)  Weekly(12)  Monthly(6)
                                  |         |            |
                            Conv1D(3,5,7) Conv1D(3,5,7) Conv1D(3,5,7)
                                  |         |            |
                             ResBlock1D  ResBlock1D  ResBlock1D
                                  |         |            |
                                LSTM       LSTM         LSTM
                                  \         |          /
                                   \        |         /
                                    [Concatenate (288)]
                                            |
                                      Linear (128)
                                            |
                                      Linear (32)
                                            |
                                       Output (3) --> [Vol Trend Probabilities]
```

### Multi-Timeframe CNN-LSTM Volatility Model

The model processes spatial patterns and temporal sequences by feeding features into three separate structural paths representing daily, weekly, and monthly observations.

*   **Temporal Scaling Paths**:
    *   **Daily path**: Evaluates the trailing 21 trading days (1 month).
    *   **Weekly path**: Evaluates the trailing 12 trading weeks (3 months).
    *   **Monthly path**: Evaluates the trailing 6 trading months (2 quarters).
*   **Engineered Feature Set (22 Inputs)**:
    1.  `RSI_14`: Normalized 14-period Relative Strength Index.
    2.  `MACD`, `MACD_Signal`, `MACD_Hist`: Normalized trend indicators.
    3.  `Stoch_K`, `Stoch_D`: Stochastic Oscillator indices.
    4.  `Williams_R`: Williams %R value.
    5.  `EMA9_Dist`, `EMA21_Dist`, `EMA50_Dist`: Distance metrics between spot price and EMAs.
    6.  `ADX`: Average Directional Index.
    7.  `BB_Width`, `BB_Position`: Bollinger Band width and price positioning.
    8.  `ATR_Norm`: Average True Range normalized by the asset price.
    9.  `ret_1d`, `ret_5d`, `ret_10d`: Multi-horizon log returns.
    10. `HL_Ratio`, `OC_Ratio`: High-Low ratio and Open-Close spread ratio.
    11. `Gap`: Gap opening percentages.
    12. `vol_momentum`: Trailing trading volume normalized by its 10-day SMA.
    13. `OBV_Norm`: Normalized On-Balance Volume.
    14. **Macro Confluences**: Local VIX momentum, 10-year Treasury Yield momentum (TNX), and US Dollar index momentum (DXY).

### Model Architecture and Layers
*   **Multi-Kernel Conv1D Layers**: Each path passes inputs through 1D convolutional layers with kernel sizes of 3, 5, and 7 to capture short-term, medium-term, and long-term momentum structures.
*   **Residual Blocks (`ResBlock1D`)**: Skip connections with Batch Normalization and GELU activation bypass deep layers to avoid vanishing gradients.
*   **LSTM Cells**: Process sequential dependencies along each temporal path.
*   **Dense Projection Head**: Concatenates output vectors, applies a 20% Dropout regularization layer, and projects values into a softmax layer to output probabilities for the three target classes.

### Async Thread Pool Offloading
Running deep learning models like PyTorch CNN-LSTM directly inside asynchronous coroutines can cause performance degradation because CPU-bound tensor arithmetic blocks the cooperative FastAPI event loop. To prevent this, model prediction is executed inside a background thread pool executor via `asyncio.to_thread(_run_forward, ...)` inside `CnnPredictorService.predict`. This ensures the web server remains responsive to simultaneous WebSocket and HTTP clients.

---

## 6. NLP Headline Sentiment Engine

Headline sentiment analysis uses the **ProsusAI/FinBERT` model, a BERT architecture pre-trained on financial text.

```
                              +---------------------------------------+
                              |          FastAPI Request Thread       |
                              +-------------------+-------------------+
                                                  |
                                                  | (Submit Text Task)
                                                  v
                              +-------------------+-------------------+
                              |          ThreadPoolExecutor           |
                              |             (max_workers=1)           |
                              |                                       |
                              |   +-------------------------------+   |
                              |   |    FinBERT Transformer Model  |   |
                              |   |     (Tokenize & Run Logits)   |   |
                              |   +-------------------------------+   |
                              +-------------------+-------------------+
                                                  |
                                                  | (Return Sentiment DTO)
                                                  v
                              +-------------------+-------------------+
                              |          FastAPI Response Path        |
                              +---------------------------------------+
```

### Thread Pool Isolation for Concurrency

*   **Problem Statement**: FinBERT transformer inferences are CPU/GPU intensive. Executing them directly in FastAPI's cooperative multitasking loop (`async/await`) would block the single-threaded event loop, delaying WebSocket transmissions and API requests.
*   **Solution**: The sentiment system isolates the model instantiation inside a singleton wrapper, executing all tokenization and inference steps inside a `ThreadPoolExecutor` limited to a single worker thread (`max_workers=1`). This setup avoids GPU memory thrashing and keeps the FastAPI event loop responsive.
*   **Pipeline Logic**:
    1.  Headline strings are pushed to the executor's queue.
    2.  Inputs are tokenized with truncation ($512$ max tokens) and dynamic padding.
    3.  The model evaluates inputs and outputs logits: `outputs = Model(**inputs).logits`.
    4.  Softmax normalization converts logits into probability scores for positive, negative, and neutral classes.
    5.  Scores are mapped to classification labels: `positive` $\rightarrow$ `BULLISH`, `negative` $\rightarrow$ `BEARISH`, `neutral` $\rightarrow$ `NEUTRAL`.

---

## 7. Frontend User Interface Architecture

The front-end is designed as a high-density, interactive Single-Page Application (SPA) built using vanilla HTML5, CSS3, and JavaScript, modeled after professional trading terminals.

### Glassmorphism & High-Density UI Design
*   **Aesthetic System**: Uses a dark glassmorphic design featuring deep violet backgrounds (`#1e1b4b`), semi-transparent slate card backdrops, and bright green/red visual cues.
*   **Compact 25-Column Grid Layout**: Displays Call Open Interest, volume, implied volatility, bid/ask prices, strikes, and Put parameters side-by-side. The layout utilizes compact margins to fit all columns without horizontal scrolling.
*   **Sticky Table Headers**: Structured so headers remain floating at the top during table body scrolling. A background color fills the table headers to prevent data rows from leaking through.
*   **Dynamic Class States**:
    *   `itm-shaded`: Shaded background (`#fffbe6`) dynamically applied to In-The-Money (ITM) options (Calls where $K < S_0$, Puts where $K > S_0$).
    *   `bs-underpriced` / `bs-overpriced`: Cells comparing live market prices against calculated fair prices. Underpriced options show in teal green, and overpriced ones highlight in orange.

### Client-Side Math Simulation
To avoid unnecessary network round-trips when adjusting simulation parameters, the client browser runs an implementation of the BSM model using Hastings' approximation of the cumulative normal distribution:

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

This math engine calculates options greeks dynamically inside the client browser as users modify parameters via the UI's control panel.

---

## 8. Deployment, Orchestration & Process Management

AlphaStreams V2 is packaged inside a single Docker image designed to run both the core backend and its dependency services concurrently.

### Supervisord Process Priorities

`supervisord` acts as the process manager within the container, launching and monitoring components according to a defined startup priority sequence:

```
+-------------------------------------------------------------+
|                       DOCKER CONTAINER                      |
|                                                             |
|   +-----------------------------------------------------+   |
|   |                  SUPERVISORD DAEMON                 |   |
|   |                                                     |   |
|   |  +---------+   +----------+   +----------+          |   |
|   |  | FastAPI |   | Postgres |   |  Redis   |          |   |
|   |  |   (30)  |   |   (20)   |   |   (10)   |          |   |
|   |  +---------+   +----------+   +----------+          |   |
|   |                                                     |   |
|   |  +---------+   +----------+   +----------+          |   |
|   |  | Celery  |   |  Celery  |   | Options  |          |   |
|   |  | Worker  |   |   Beat   |   | Sub (PDE)|          |   |
|   |  |   (40)  |   |   (45)   |   |   (60)   |          |   |
|   |  +---------+   +----------+   +----------+          |   |
|   |                                                     |   |
|   |  +-------------+   +---------------+                |   |
|   |  | Sentiment   |   | Read-Model    |                |   |
|   |  | Orchestrator|   | Updater       |                |   |
|   |  |   (50)  |   |   (55)   |                |   |
|   |  +-------------+   +---------------+                |   |
|   +-----------------------------------------------------+   |
+-------------------------------------------------------------+
```

*   **`redis`** (Priority 10): Starts first to establish the messaging layer.
*   **`postgresql`** (Priority 20): Initializes the database storage engine.
*   **`app`** (Priority 30): Launches the FastAPI ASGI worker (`uvicorn app.main:app`).
*   **`celery` / `celery-beat`** (Priority 40/45): Initializes background task scheduling.
*   **`sentiment-orchestrator`** (Priority 50): Starts the NLP headline scoring service.
*   **`read-model-updater`** (Priority 55): Coordinates read cache updates from streams.
*   **`ingestion-orchestrator`** (Priority 56): Manages data ingestion pipelines.
*   **`options-subscriber`** (Priority 60): Activates the Crank-Nicolson PDE option pricer.

### Container Bootstrapping Sequence (`start.sh`)

When the Docker container starts, `start.sh` executes the following initialization steps:
1.  **System Environments Setup**: Configures standard directory permissions for `/var/run/postgresql` and the `postgres` system user.
2.  **Database Directory Audit**: If the database directory is empty:
    *   Runs PostgreSQL's `initdb` command.
    *   Appends `shared_preload_libraries = 'timescaledb'` to `postgresql.conf` to enable the TimescaleDB extension.
    *   Starts a temporary database daemon instance, creates the `NexusQuantDB` database, and registers the TimescaleDB extension.
    *   Executes `init_schema.sql` to generate database tables and hypertables.
3.  **Locale Initialization**: Sets the local timezone to `Asia/Kolkata` and updates default locale files inside configuration templates.
4.  **Process Handover**: Handover control to `supervisord` to manage the lifecycle of all services.

### High-Performance Event Loops (`uvloop`)
To maximize networking performance on Unix platforms inside the Docker container, standalone Python entry point processes (`options_subscriber` and `sentiment_orchestrator`) conditionally import and install `uvloop` upon startup. This drops overheads associated with standard `asyncio` event loops by leveraging `libuv` under the hood.

---

## 9. Regulatory Compliance & Disclaimers

### SEBI Risk Disclosure Mandate
In compliance with the Securities and Exchange Board of India (SEBI) guidelines on trading in equity derivatives, the system displays the following warning on the user dashboard:

> "9 out of 10 individual traders in equity derivatives segment incurred net losses, averaging ₹50,000 loss per year, with an additional 28% in transaction costs."

### Research & Investment Disclaimer
All analytical metrics, BSM theoretical prices, Crank-Nicolson PDE solutions, and PyTorch volatility forecasts generated by this platform are for educational and research purposes only. This system does not provide investment advice, and the platform operators are not registered SEBI Investment Advisers (IA) or Research Analysts (RA). Users are advised to verify all pricing outputs independently before executing trades in active financial markets.
