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

### Auth & User Profile Endpoints
- **`POST /v1/auth/signup`**: Registers a new user account with email and password via Supabase Auth.
- **`POST /v1/auth/login`**: Authenticates user credentials and returns session tokens.
- **`GET /v1/auth/me`**: Fetches authenticated user profile and metadata.
- **`POST /v1/auth/profile`**: Updates user full name and metadata.

### GET `/v1/symbols` — System Watchlist
Returns the default watchlist from configuration settings.

### GET `/v1/symbols/search` — Active Instrument Autocomplete
Searches across the 2,000+ NSE equity and indices catalog.
- **Query Parameter**: `q` (e.g. `?q=RELIANCE`)

### GET `/health` — System Health Status
Returns `{"status": "ok"}` when healthy.

---

## 2. WebSocket Real-Time Stream

### Endpoints:
- `WS /ws/options/{symbol}` — Streams live option chain recalculations, spot prices, and BSM metrics.
- `WS /ws/derivatives/{symbol}` — Streams real-time tick updates for derivative analytics.

### Message Payload Types
When subscribed, the system pushes JSON payloads containing the `type` field:
- **`price`**: Dispatched on spot price updates.
- **`options`**: Dispatched on option chain recalculations.
- **`trigger`**: Dispatched on abnormal volume/price spikes.
- **`alert`**: Dispatched on alert notifications.
