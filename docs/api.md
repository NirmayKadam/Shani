# API Reference & Documentation

FastAPI auto-generates interactive documentation which is served at:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 1. REST Endpoints

### Derivatives & Analytics

#### GET `/v1/derivatives/{symbol}` — Option Chain Analytics
Returns the options chain evaluated by the Crank-Nicolson PDE solver, PCR, volume, and open interest summary.
- **Example**: `GET /v1/derivatives/NIFTY`

#### GET `/v1/derivatives/{symbol}/technicals` — Technical Indicators & Signals
Returns precomputed technical indicator metrics (RSI, MACD, Bollinger Bands, ATR, Moving Averages, Pivot Points) and composite bull/bear sentiment signals computed using live historical market OHLC price history via `yfinance`.
- **Example**: `GET /v1/derivatives/NIFTY/technicals?spot=22450.0`

---

### Pricer

#### GET `/v1/pricer/ticker/{symbol}` — Live Options Parameters
Returns live option chain parameters, spot price, implied volatility, risk-free rate, dividend yield, and available strike grids for Black-Scholes-Merton calculations. Reads from Redis cache first, falling back to live adapter fetch.
- **Example**: `GET /v1/pricer/ticker/NIFTY`

#### POST `/v1/pricer/calculate` — BSM Pricing Calculator
Performs high-precision analytical Black-Scholes-Merton pricing on arbitrary parameters.
- **Request Body**:
  ```json
  {
    "S0": 22450.0,
    "K": 22500.0,
    "T_days": 5,
    "r": 6.5,
    "sigma": 12.8,
    "option_type": "call",
    "q": 1.2
  }
  ```

---

### Ingestion

#### GET `/v1/ingestion/nse/option-chain/{symbol}` — NSE Raw Option Chain Ingestion
Fetches raw option chain payload from NSE API adapter for the specified symbol.
- **Example**: `GET /v1/ingestion/nse/option-chain/NIFTY`

---

### Symbols

#### GET `/v1/symbols` — System Watchlist
Returns the default watchlist from configuration settings.

#### GET `/v1/symbols/search` — Active Instrument Autocomplete
Searches across the 2,000+ NSE equity and indices catalog.
- **Query Parameter**: `q` (e.g. `?q=RELIANCE`)

---

### Notifications & Alerts

#### POST `/v1/notifications/alerts` — Create Alert Rule
Creates a new real-time market alert rule with configurable condition types, thresholds, channels, and cooldown policies.
- **Request Body**:
  ```json
  {
    "symbol": "NIFTY",
    "condition_type": "price_above",
    "threshold": 23000.0,
    "channels": ["webhook"],
    "cooldown_seconds": 300,
    "webhook_url": "https://example.com/hook"
  }
  ```

#### GET `/v1/notifications/alerts` — List Alert Rules
Returns all active alert rules, optionally filtered by symbol.
- **Query Parameter**: `symbol` (optional, e.g. `?symbol=NIFTY`)

#### GET `/v1/notifications/alerts/{rule_id}` — Get Alert Rule
Returns details of a specific alert rule by UUID.

#### DELETE `/v1/notifications/alerts/{rule_id}` — Delete Alert Rule
Deletes an existing alert rule by UUID. Returns `204 No Content` on success.

---

### System

#### GET `/config` — Client Application Configuration
Returns public environment configuration (Supabase URL and anon key) used by frontend JS.

#### GET `/health` — System Health Status
Returns health status for API, Redis, and Database connections.

### Client-Side Auth & User Profile (Supabase JS SDK)
Authentication, signups, logins, and profile metadata updates are performed directly client-side via the Supabase JS SDK (`supabase.auth.*` and `public.users` table), initialized using credentials from `/config`.

---

## 2. WebSocket Real-Time Stream

### Endpoint:
- `WS /v1/ws/{symbol}` — Single real-time streaming endpoint for price updates, option chain recalculations, volume triggers, and alert notifications.

### Message Payload Types
When subscribed, the system pushes JSON payloads containing the `type` field:
- **`price`**: Dispatched on spot price updates.
- **`options`**: Dispatched on option chain recalculations.
- **`trigger`**: Dispatched on abnormal volume/price spikes.
- **`alert`**: Dispatched on alert notifications matching user-defined rules.
