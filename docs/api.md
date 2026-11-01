# API Reference & Documentation

FastAPI auto-generates interactive documentation which is served at:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 1. REST Endpoints

### Derivatives & Analytics

#### GET `/v1/derivatives/{symbol}` â€” Option Chain Analytics
Returns the options chain evaluated by the Crank-Nicolson PDE solver, PCR, volume, and open interest summary.
- **Example**: `GET /v1/derivatives/NIFTY`

#### GET `/v1/derivatives/{symbol}/technicals` â€” Technical Indicators & Signals
Returns precomputed technical indicator metrics (RSI, MACD, Bollinger Bands, ATR, Moving Averages, Pivot Points) and composite bull/bear sentiment signals computed using live historical market OHLC price history via `yfinance`.
- **Example**: `GET /v1/derivatives/NIFTY/technicals?spot=22450.0`

---

### Pricer

#### GET `/v1/pricer/ticker/{symbol}` â€” Live Options Parameters
Returns live option chain parameters, spot price, implied volatility, risk-free rate, dividend yield, and available strike grids for Black-Scholes-Merton calculations. Reads from Redis cache first, falling back to live adapter fetch.
- **Example**: `GET /v1/pricer/ticker/NIFTY`

#### POST `/v1/pricer/calculate` â€” BSM Pricing Calculator
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

#### GET `/v1/ingestion/nse/option-chain/{symbol}` â€” NSE Raw Option Chain Ingestion
Fetches raw option chain payload from NSE API adapter for the specified symbol.
- **Example**: `GET /v1/ingestion/nse/option-chain/NIFTY`

---

### Symbols

#### GET `/v1/symbols` â€” System Watchlist
Returns the default watchlist from configuration settings.

#### GET `/v1/symbols/search` â€” Active Instrument Autocomplete
Searches across the 2,000+ NSE equity and indices catalog.
- **Query Parameter**: `q` (e.g. `?q=RELIANCE`)

---

### Notifications & Alerts

All alert endpoints require `Authorization: Bearer <Supabase access token>`. Rules belong to the user who created them; other users' rules return `404`. Alerts are symbol-level: `ABOVE_PRICE` and `BELOW_PRICE` compare the spot price, `IV_SPIKE` compares the ATM call IV in percent. A rule fires when its condition **crosses** from false to true (not on every tick while it stays true), at most once per `cooldown_seconds`.

#### POST `/v1/notifications/alerts` — Create Alert Rule
- **Request Body**:
  ```json
  {
    "symbol": "NIFTY",
    "condition_type": "ABOVE_PRICE",
    "threshold": 23000.0,
    "channels": ["WEBSOCKET", "WEBHOOK"],
    "cooldown_seconds": 300,
    "webhook_url": "https://example.com/hook"
  }
  ```
- `condition_type`: `ABOVE_PRICE`, `BELOW_PRICE` or `IV_SPIKE`. `channels`: any of `WEBSOCKET`, `WEBHOOK`, `EMAIL` (`WEBHOOK` needs `webhook_url`, `EMAIL` needs `email_destination`). `cooldown_seconds`: 10 to 86400.
- The symbol is stored in its canonical form (`RELIANCE` becomes `RELIANCE.NS`).
- Webhook URLs must be HTTPS and must not resolve to a private, loopback or link-local address.
- **Response** (`201`): the rule, plus `webhook_secret` when a webhook is configured. The secret is returned only once. Each webhook POST carries `X-AlphaStreams-Signature: <hex HMAC-SHA256 of the raw body, keyed with that secret>`; delivery is attempted up to `WEBHOOK_MAX_ATTEMPTS` times (default 3) with exponential backoff.

#### GET `/v1/notifications/alerts` — List Alert Rules
Returns the caller's active rules, optionally filtered by symbol.
- **Query Parameter**: `symbol` (optional, e.g. `?symbol=NIFTY`)

#### GET `/v1/notifications/alerts/{rule_id}` — Get Alert Rule
Returns one of the caller's rules by UUID.

#### DELETE `/v1/notifications/alerts/{rule_id}` — Delete Alert Rule
Deletes one of the caller's rules by UUID. Returns `204 No Content` on success.

---
### System

#### GET `/config` â€” Client Application Configuration
Returns public environment configuration (Supabase URL and anon key) used by frontend JS.

#### GET `/health` â€” System Health Status
Returns health status for API, Redis, and Database connections.

### Client-Side Auth & User Profile (Supabase JS SDK)
Authentication, signups, logins, and profile metadata updates are performed directly client-side via the Supabase JS SDK (`supabase.auth.*` and `public.users` table), initialized using credentials from `/config`.

---

## 2. WebSocket Real-Time Stream

### Endpoint:
- `WS /v1/ws/{symbol}` — Single real-time streaming endpoint for price updates, option chain recalculations, volume triggers, and alert notifications.

### Authentication
Market data is public. To receive your own alerts, send `{"action": "auth", "token": "<Supabase access token>"}` after connecting (the token is kept out of the URL so it is not written to access logs). The server replies `{"type": "auth", "ok": true|false}`.

### Message Payload Types
When subscribed, the system pushes JSON payloads containing the `type` field:
- **`price`**: Dispatched on spot price updates.
- **`options`**: Dispatched when a chain has been re-priced. Carries only `{symbol, last_updated}`; fetch the chain from `/v1/derivatives/{symbol}` or `/v1/pricer/ticker/{symbol}`.
- **`trigger`**: Dispatched on abnormal volume/price spikes.
- **`alert`**: Dispatched only to sockets authenticated as the rule's owner. The text is in `data.message`.
- **`ping`** / **`pong`**: keep-alive. Clients may send `{"action": "ping"}`.

### Close Codes
| Code | Meaning |
|---|---|
| 4000 | Idle client closed by the server |
| 4001 | Invalid or unsupported symbol |
| 4002 | Slow client (send queue full) closed by the server |
| 4029 | Connection or symbol limit reached |

Clients should reconnect with backoff on any close while a symbol is selected.