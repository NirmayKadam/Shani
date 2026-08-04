# API Reference & Documentation

FastAPI auto-generates interactive documentation which is served at:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 1. REST Endpoints

### GET `/v1/derivatives/{symbol}` — Option Chain Analytics
Returns the options chain evaluated by the Crank-Nicolson PDE solver, PCR, volume, and open interest summary.
- **Example**: `GET /v1/derivatives/NIFTY`

### GET `/v1/derivatives/{symbol}/technicals` — Technical Indicators & Signals
Returns precomputed technical indicator metrics (RSI, MACD, Bollinger Bands, ATR, Moving Averages, Pivot Points) and composite bull/bear sentiment signals computed using live historical market OHLC price history via `yfinance`.
- **Example**: `GET /v1/derivatives/NIFTY/technicals`

### GET `/v1/analytics/options/{symbol}/parameters` — Option Chain Parameters
Returns option chain parameters, spot price, risk-free rate, dividend yield, and available strike grids for Black-Scholes-Merton calculations.
- **Example**: `GET /v1/analytics/options/NIFTY/parameters`

### POST `/v1/pricer/calculate` — BSM Pricing Calculator
Performs high-precision, client-side equivalent analytical Black-Scholes-Merton pricing on arbitrary parameters.
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

### GET `/v1/ingestion/nse/option-chain/{symbol}` — NSE Raw Option Chain Ingestion
Fetches raw option chain payload from NSE API adapter for the specified symbol.
- **Example**: `GET /v1/ingestion/nse/option-chain/NIFTY`

### GET `/config` — Client Application Configuration
Returns public environment configuration (Supabase URL and anon key) used by frontend JS.

### Client-Side Auth & User Profile (Supabase JS SDK)
Authentication, signups, logins, and profile metadata updates are performed directly client-side via the Supabase JS SDK (`supabase.auth.*` and `public.users` table), initialized using credentials from `/config`.

### GET `/v1/symbols` — System Watchlist
Returns the default watchlist from configuration settings.

### GET `/v1/symbols/search` — Active Instrument Autocomplete
Searches across the 2,000+ NSE equity and indices catalog.
- **Query Parameter**: `q` (e.g. `?q=RELIANCE`)

### GET `/health` — System Health Status
Returns health status for API, Redis, and Database connections.

---

## 2. WebSocket Real-Time Stream

### Endpoint:
- `WS /v1/ws/{symbol}` — Single real-time streaming endpoint for price updates, option chain recalculations, volume triggers, and alert notifications.

### Message Payload Types
When subscribed, the system pushes JSON payloads containing the `type` field:
- **`price`**: Dispatched on spot price updates.
- **`options`**: Dispatched on option chain recalculations.
- **`trigger`**: Dispatched on abnormal volume/price spikes.
- **`alert`**: Dispatched on alert notifications.
