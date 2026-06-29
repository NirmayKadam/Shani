# API Reference & Documentation

FastAPI auto-generates interactive documentation which is served at:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 1. REST Endpoints

### GET `/v1/signals/{symbol}` — Composite Signals
Returns a consolidated overview of a ticker's market sentiment and machine learning predictions.
- **Example**: `GET /v1/signals/NIFTY`
- **Behavior**: Reads from the Redis Cache read model. If missing, dispatches a refresh request event to trigger background processing.

### GET `/v1/derivatives/{symbol}` — Option Chain Analytics
Returns the options chain evaluated by the Crank-Nicolson PDE solver, PCR, volume, and open interest summary.
- **Example**: `GET /v1/derivatives/NIFTY`

### GET `/v1/predictions/{symbol}` — Volatility Prediction
Predicts the 5-day forward volatility index shift category.
- **Example**: `GET /v1/predictions/NIFTY`
- **Output Classes**: `VOL_CRUSH` | `NEUTRAL` | `VOL_EXPAND`

### GET `/v1/pricer/ticker/{symbol}` — Option Chain Data
Returns raw or mock options chain ticks to run Black-Scholes-Merton calculations.
- **Example**: `GET /v1/pricer/ticker/NIFTY`

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

### GET `/v1/symbols` — System Watchlist
Returns the default watchlist from configuration settings.

### GET `/v1/symbols/search` — Active Instrument Autocomplete
Searches across the 2,000+ NSE equity and indices catalog.
- **Query Parameter**: `q` (e.g. `?q=RELIANCE`)

### GET `/health` — System Health Status
Returns `{"status": "ok"}` when healthy.

---

## 2. WebSocket Real-Time Stream

### Endpoint: `WS /v1/ws/{symbol}`
Streams real-time updates for the target symbol.

### Message Payload Types
When subscribed, the system pushes JSON payloads containing the `type` field:
- **`headline`**: Dispatched when new headlines are fetched.
- **`price`**: Dispatched on spot price updates.
- **`options`**: Dispatched on option chain recalculations.
- **`sentiment`**: Dispatched on single scored headlines.
- **`aggregate`**: Dispatched on multi-timeframe sentiment shifts.
- **`trigger`**: Dispatched on abnormal volume/price spikes.
