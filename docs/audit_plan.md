# Full-Stack Codebase Audit & Improvement Plan

Comprehensive audit of the AlphaStreams/Shani project — frontend → backend → DB → deployment.

---

## 1. 🔴 SECURITY ISSUES (Critical)

### 1.1 `.env` file committed with live secrets
- **File**: [.env](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/.env)
- **Problem**: `.env` is in `.gitignore` but the file contains **live Groww API JWT**, TOTP secret, PIN, Supabase keys, and DB passwords in plaintext. If this was ever committed to git history, secrets are permanently exposed.
- **Fix Options**:
  - A) Rotate ALL secrets immediately (Groww JWT, TOTP, Supabase key, DB password)
  - B) Run `git filter-branch` or `bfg` to scrub `.env` from git history
  - C) Use a secrets manager (Docker secrets, Vault, or encrypted env files)

### 1.2 `/config` endpoint leaks Supabase credentials without auth
- **File**: [main.py L172-179](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/app/main.py#L172-L179)
- **Problem**: `GET /config` returns `supabaseUrl` and `supabaseKey` to **any unauthenticated caller**. While these are publishable keys, combining them with unprotected API endpoints is risky.
- **Fix**: Add rate limiting or restrict to same-origin requests only.

### 1.3 Auth middleware is a no-op
- **File**: [auth.py](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/shared/middleware/auth.py)
- **Problem**: `APIKeyAuthMiddleware` only logs the presence of an auth header, **never rejects unauthorized requests**. All backend API endpoints (alerts CRUD, export, pricer) are completely open.
- **Fix Options**:
  - A) Validate Supabase JWT on server-side for protected routes
  - B) Implement API key validation for ingestion/admin endpoints
  - C) At minimum, restrict write endpoints (`POST /alerts`, `DELETE /alerts`) to authenticated users

### 1.4 XSS via unsanitized symbol/name injection
- **File**: [app.js L429-435](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/frontend/app.js#L429-L435)
- **Problem**: `renderSuggestions()` uses `item.symbol` and `item.name` directly in `innerHTML` without escaping. A malicious symbol name from the API could inject scripts.
- **Fix**: Use `textContent` or sanitize HTML before insertion.

### 1.5 Alert toast uses innerHTML with user data
- **File**: [app.js L2592](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/frontend/app.js#L2592)
- **Problem**: `showAlertToast()` inserts `message` parameter directly into `innerHTML`.
- **Fix**: Use `textContent` for the message portion.

### 1.6 WebSocket has no authentication
- **File**: [events_router_api.py L303-344](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/domains/analytics/api/events_router_api.py#L303-L344)
- **Problem**: Any client can connect to `/ws/{symbol}` without authentication. Could be abused for resource exhaustion.
- **Fix**: Validate a token query param or cookie before `ws.accept()`.

### 1.7 CORS is wide open (`*`)
- **File**: [settings.py L17](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/app/config/settings.py#L17) + [main.py L98-104](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/app/main.py#L98-L104)
- **Problem**: `AllowedOrigins` defaults to `*` with `allow_credentials=True`. This is an invalid and insecure CORS configuration.
- **Fix**: Set explicit allowed origins in production.

---

## 2. 🟡 DATA MOCKS & INCORRECT FALLBACKS

### 2.1 Hardcoded risk-free rate fallback
- **Files**: [app.js L526](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/frontend/app.js#L526), [pricer_router_api.py L199,305](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/domains/analytics/api/pricer_router_api.py#L199)
- **Problem**: Hardcoded `5.25` for AAPL/TSLA, `6.50` for Indian symbols. This logic is duplicated in 3+ places and will silently go stale as rates change.
- **Fix**: Centralize rate config; fetch from a reference source or make it a Settings field.

### 2.2 Fabricated bid/ask prices
- **File**: [pricer_router_api.py L235-236](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/domains/analytics/api/pricer_router_api.py#L235-L236)
- **Problem**: `bid = ltp * 0.98`, `ask = ltp * 1.02` — these are **fabricated** spread values presented as real market data.
- **Fix**: Use actual bid/ask from the data source; if unavailable, mark as `null` rather than fabricating.

### 2.3 Default IV fallback of 25%
- **Files**: [pricer_router_api.py L241](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/domains/analytics/api/pricer_router_api.py#L241), [app.js L524,962](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/frontend/app.js#L524)
- **Problem**: When IV is missing, it silently defaults to 25%. This incorrect fallback flows into BSM calculations, making all derived Greeks wrong.
- **Fix**: Display a "data unavailable" indicator instead of a fake 25% IV.

### 2.4 Dividend yield hardcoded to 0.5%
- **File**: [pricer_router_api.py L306](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/domains/analytics/api/pricer_router_api.py#L306)
- **Problem**: `dividend_yield=0.5` is returned as a blanket default. Different stocks have vastly different yields.
- **Fix**: Return `0.0` and let the user customize, or source real dividend data.

### 2.5 `historical_volatility` always returns 0.0
- **File**: [pricer_router_api.py L298](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/domains/analytics/api/pricer_router_api.py#L298)
- **Problem**: Field is always `0.0` — dead/stub data.
- **Fix**: Either compute HV from historical prices or remove the field.

---

## 3. 🟡 FRONTEND CODE ISSUES

### 3.1 Monolithic 2721-line app.js
- **Problem**: Single file handles BSM math, DOM manipulation, WebSocket, API calls, export logic, alerts, theme, particles — **extremely hard to maintain**.
- **Fix**: Split into modules (e.g., `bsm-engine.js`, `websocket.js`, `export.js`, `technicals.js`, `theme.js`).

### 3.2 Duplicate BSM calculation (frontend + backend)
- **Problem**: Identical BSM pricing logic exists in both `app.js` (L188-270) and `pricer_router_api.py` (L325-394). Bug fixes must be applied twice.
- **Fix**: Choose one source of truth — either compute server-side and serve, or keep client-side only and remove the unused `/calculate` endpoint.

### 3.3 Heavy inline styles in HTML
- **File**: [dashboard.html](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/frontend/dashboard.html) — dozens of `style="..."` attributes
- **Problem**: Inline styles bypass theme variables, making dark/light mode inconsistent. The pivot level grid (L306-314) uses hardcoded colors that won't adapt to dark mode.
- **Fix**: Move all inline styles to CSS classes using theme variables.

### 3.4 Table rebuilt via innerHTML on every update
- **File**: [app.js L1006-1214](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/frontend/app.js#L1006-L1214)
- **Problem**: `recalculateAndRender()` destroys and rebuilds the entire table DOM on every price tick. With 40+ rows × 19 columns, this causes layout thrashing.
- **Fix**: Use a virtual DOM diffing approach, or update only changed cell values.

### 3.5 Particle animation runs at 60fps continuously
- **File**: [app.js L2324-2419](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/frontend/app.js#L2324-L2419)
- **Problem**: `O(n²)` particle connection check runs every frame. With 100 particles, that's ~5000 distance checks × 60fps = 300,000 operations/second.
- **Fix Options**:
  - A) Reduce to 30fps via `setTimeout` throttle
  - B) Use spatial partitioning (grid cells) for proximity checks
  - C) Pause animation when tab is not visible (`document.hidden`)

### 3.6 Missing `meta description` for SEO
- **File**: [dashboard.html](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/frontend/dashboard.html)
- **Problem**: No `<meta name="description">` tag.
- **Fix**: Add appropriate meta description.

### 3.7 CSS version cache-busting is manual
- **File**: [dashboard.html L11](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/frontend/dashboard.html#L11)
- **Problem**: `style.css?v=2.6.4` requires manual version bumps. Easy to forget and serve stale CSS.
- **Fix**: Use a build-time hash or content hash.

### 3.8 No JS cache busting for app.js
- **Problem**: `app.js` has no version query param at all, meaning browsers may cache old versions indefinitely.
- **Fix**: Add a version/hash query parameter to the script tag.

---

## 4. 🟡 FRONTEND UI ISSUES

### 4.1 Pivot levels grid not theme-aware
- **File**: [dashboard.html L306-314](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/frontend/dashboard.html#L306-L314)
- **Problem**: Hardcoded `#fef2f2`, `#ecfdf5` etc. — these light-mode colors will look wrong in dark mode.
- **Fix**: Replace with CSS variables (e.g., `var(--pivot-resistance-bg)`).

### 4.2 Alert modal HTML missing from dashboard.html
- **Problem**: `setupAlertsModal()` references `#alerts-modal`, `#alerts-modal-close`, `#create-alert-form`, `#active-alerts-list` — but these elements don't exist in the HTML. The bell button does nothing useful.
- **Fix**: Add the alerts modal HTML to `dashboard.html`.

### 4.3 BSM Modal HTML missing
- **Problem**: `setupBsmModal()` references `#bsm-modal` but the modal HTML with control sliders/ATM metrics is not in `dashboard.html`. The BSM Control Panel button likely does nothing.
- **Fix**: Add the BSM modal HTML or verify it's loaded dynamically.

### 4.4 No mobile responsiveness
- **Problem**: The option chain table with 19 columns is not usable on mobile. No responsive breakpoints for the filter bar or action links.
- **Fix**: Add responsive layouts; consider horizontal scroll or stacked card view for mobile.

---

## 5. 🟢 SPEED & SPACE OPTIMIZATION

### 5.1 XLSX library loaded from CDN without tree-shaking
- **Problem**: SheetJS (XLSX) is likely a large library loaded on every page visit, even if user never exports.
- **Fix**: Lazy-load the XLSX script only when export is triggered.

### 5.2 SVG logo is 1.2MB
- **File**: `Shani-logo.svg` — 1,249,812 bytes
- **Problem**: An SVG logo should typically be < 10KB. 1.2MB is extremely large and slows initial page load.
- **Fix**: Optimize with SVGO or replace with a properly sized SVG.

### 5.3 Bull image is 5.5MB PNG
- **File**: `bull_image.png` — 5,591,373 bytes
- **Problem**: Massive uncompressed image.
- **Fix**: Convert to WebP (typically 80% smaller), serve responsive sizes.

### 5.4 Redis cache TTL is 600s (10 min) for market data
- **File**: [pricer_router_api.py L134,142](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/domains/analytics/api/pricer_router_api.py#L134)
- **Problem**: Market data cached for 10 minutes means stale prices during active trading.
- **Fix**: Reduce to 30-60s for price data; keep 5-10 min for options chain.

### 5.5 `run_in_executor` for sync SymbolValidator
- **File**: [pricer_router_api.py L61-63](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/domains/analytics/api/pricer_router_api.py#L61-L63)
- **Problem**: CPU-bound symbol validation runs in thread pool executor on every ticker request.
- **Fix**: Make SymbolValidator async-native or cache results.

### 5.6 Duplicate Celery tasks dispatched
- **File**: [events_router_api.py L286-287](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/domains/analytics/api/events_router_api.py#L286-L287)
- **Problem**: Both `poll_options.delay(symbol)` AND `fetch_and_publish_options.delay(symbol)` are dispatched simultaneously — likely doing the same work twice.
- **Fix**: Consolidate into a single task.

### 5.7 No GZip for static files
- **Problem**: GZipMiddleware is added with `minimum_size=1000`, but `StaticFiles` mount may bypass middleware. The 115KB `app.js` should be pre-compressed.
- **Fix**: Pre-compress static assets or verify GZip applies to static file serving.

### 5.8 Uvicorn runs with single worker
- **File**: [supervisord.conf L29](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/docker/supervisord.conf#L29)
- **Problem**: `uvicorn app.main:app --host 0.0.0.0 --port 8000` runs 1 worker.
- **Fix**: Add `--workers 2` or use Gunicorn with Uvicorn workers for production.

---

## 6. 🔵 DATABASE ISSUES & OPTIMIZATION

### 6.1 No indexes on TickData beyond hypertable
- **File**: [init_schema.sql](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/scripts/init_schema.sql)
- **Problem**: `TickData` has no composite index on `(Symbol, Timestamp)`. Queries filtering by symbol will do sequential scans within chunks.
- **Fix**: Add `CREATE INDEX idx_tickdata_symbol_time ON TickData (Symbol, Timestamp DESC);`

### 6.2 7-day retention may be too aggressive
- **File**: [init_schema.sql L24](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/scripts/init_schema.sql#L24)
- **Problem**: Multi-day export supports up to 90 days, but TickData retains only 7 days. Exports beyond 7 days will have no data.
- **Fix**: Align retention policy with export capability (90 days), or use continuous aggregates for older data.

### 6.3 No migration versioning system
- **Problem**: Migrations are raw SQL files run in `start.sh` without tracking which have been applied. Re-running could fail or cause duplicates.
- **Fix**: Use Alembic, or add a `schema_migrations` table to track applied scripts.

### 6.4 DB pool `min_size=5` may be excessive
- **File**: [database.py L48](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/shared/infrastructure/database.py#L48)
- **Problem**: Maintaining 5 idle connections in a single-container deployment wastes resources.
- **Fix**: Reduce to `min_size=2`.

### 6.5 `dump.rdb` (3MB) committed to repo
- **Problem**: Redis dump file shouldn't be in the repository.
- **Fix**: It's in `.gitignore` — verify it's not tracked. If tracked, remove from git.

### 6.6 `celerybeat-schedule` committed
- **Problem**: Binary state file in the repo.
- **Fix**: Same as above — verify not tracked.

---

## 7. 🔵 DEPLOYMENT OPTIMIZATIONS

### 7.1 All services in single container (anti-pattern)
- **Problem**: PostgreSQL, Redis, FastAPI, Celery worker, Celery beat, ingestion orchestrator, options subscriber, and notification subscriber all run in ONE container via supervisord. This prevents independent scaling and complicates health checks.
- **Fix Options**:
  - A) **Quick**: Keep monolith but document limitations
  - B) **Proper**: Split into separate containers in docker-compose (postgres, redis, app, celery-worker, celery-beat)

### 7.2 Docker volume mount overwrites container code
- **File**: [docker-compose.yml L14](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/docker-compose.yml#L14)
- **Problem**: `.:/app` volume mount means local Windows files override container files. This is fine for dev but breaks production.
- **Fix**: Remove volume mount for production; use a separate `docker-compose.prod.yml`.

### 7.3 No multi-stage Docker build
- **File**: [Dockerfile](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/Dockerfile)
- **Problem**: Build tools, test dependencies, and source code all remain in the final image. Image is unnecessarily large.
- **Fix**: Use multi-stage build to separate build and runtime stages.

### 7.4 Heavy unused Python dependencies
- **File**: [requirements.txt](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/requirements.txt)
- **Problem**: `matplotlib`, `seaborn`, `scikit-learn` are listed but likely unused in runtime. They add ~500MB to the Docker image.
- **Fix**: Split into `requirements.txt` (runtime) and `requirements-dev.txt` (dev/analysis).

### 7.5 No resource limits in docker-compose
- **Problem**: Container can consume unlimited CPU/memory.
- **Fix**: Add `deploy.resources.limits` for memory and CPU.

### 7.6 Redis runs without password
- **File**: [supervisord.conf L7](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/docker/supervisord.conf#L7)
- **Problem**: `redis-server` starts with no authentication. Combined with port 6379 being exposed, anyone can connect.
- **Fix**: Add `--requirepass` flag or use a redis.conf with authentication.

### 7.7 Postgres pg_hba.conf allows all connections with md5
- **File**: [start.sh L19-20](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/docker/start.sh#L19-L20)
- **Problem**: `host all all 0.0.0.0/0 md5` allows connections from any IP. Combined with port 5433 exposed, DB is accessible externally.
- **Fix**: Restrict to `127.0.0.1/32` for in-container access only.

### 7.8 `.env` included in Docker build context
- **File**: [.dockerignore L1](file:///d:/Nirmay%20pc/ENGINEERING/projects/MarketSentimentAnalysis2/.dockerignore#L1)
- **Problem**: `.env` is in `.dockerignore` ✅ — this is correct. But `COPY . .` in the Dockerfile would include it if `.dockerignore` is misconfigured.
- **Status**: Currently correct, but fragile.

---

## 8. 🟢 CODE QUALITY

### 8.1 `test_export.xlsx` committed to repo root
- **Problem**: Test artifact in project root.
- **Fix**: Delete and add `*.xlsx` to `.gitignore`.

### 8.2 No type hints on frontend (vanilla JS)
- **Problem**: 2700+ lines of untyped JavaScript.
- **Fix**: Consider migrating to TypeScript for maintainability (long-term).

### 8.3 Duplicate date calculation logic
- **Problem**: Days-to-expiry calculation is copy-pasted in 6+ places across `app.js` (L544-554, L949-958, L1237-1248, L1378-1388, L1829-1839, L1918-1923).
- **Fix**: Extract into a reusable `calculateDaysToExpiry(expiryDateStr)` function.

---

## Priority Ranking

| Priority | Category | Items |
|----------|----------|-------|
| 🔴 P0 | Security | 1.1, 1.3, 1.6, 1.7 |
| 🔴 P1 | Security | 1.2, 1.4, 1.5 |
| 🟡 P2 | Data Integrity | 2.1, 2.2, 2.3, 2.4, 2.5 |
| 🟡 P2 | UI Bugs | 4.1, 4.2, 4.3 |
| 🟢 P3 | Performance | 5.1, 5.2, 5.3, 5.5, 5.7 |
| 🟢 P3 | DB | 6.1, 6.2, 6.3 |
| 🔵 P4 | Deployment | 7.1, 7.3, 7.4, 7.6, 7.7 |
| 🔵 P5 | Code Quality | 3.1, 3.4, 8.3 |

---

## Verification Plan

### Automated
- Run `pytest` to confirm no regressions
- Docker build + health check endpoint validation
- Lighthouse audit for frontend perf after asset optimization

### Manual
- Verify dark/light mode consistency on all components
- Test alert creation/deletion flow end-to-end
- Confirm export functionality for both single-day and multi-day
- Validate WebSocket reconnection behavior

## Open Questions

> [!IMPORTANT]
> 1. Which items would you like me to tackle first? I recommend starting with **Security (Section 1)** then **Data Mocks (Section 2)**.
> 2. Is this app currently deployed to production, or only running locally via Docker? This affects urgency of security fixes.
> 3. For the monolith-to-multi-container split (7.1) — is this something you want to address now, or keep for later?
