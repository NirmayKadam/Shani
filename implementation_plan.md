# Options PDE Solver Implementation Plan

Implementation of the Crank-Nicolson PDE solver and redis streaming for options.

## User Review Required

> [!WARNING]
> `yfinance` does not support options chains for Indian (`.NS` / `.BO`) tickers. Returns empty `()`. 
>
> **Solution for now:** In `fetch_and_publish_options`, if `expirations` is empty, generate synthetic option strikes (e.g. +/- 10% from spot) so the PDE pipeline can run and prove the architecture works. Later, swap `yfinance` for Zerodha/Upstox API to get real Indian options.

## Proposed Changes

### 1. Analytics Domain

#### [NEW] domains/analytics/application/derivatives/pde_solver.py
- Implement `CrankNicolsonPDE` class exactly as provided.
- Dependency: `scipy.sparse`.

#### [NEW] domains/analytics/infrastructure/options_subscriber.py
- Implement daemon to consume `stream:options.raw_fetched`.
- Feed through `CrankNicolsonPDE` for put/call.
- Publish valid chain to `stream:options.priced`.
- Stream via pub/sub `market.options_updated.{symbol}`.

### 2. Ingestion Domain

#### [MODIFY] domains/ingestion/application/tasks/market_tasks.py
- Add `fetch_and_publish_options` celery task.
- Generate synthetic option strikes if `yfinance` returns an empty list for NSE.

### 3. API Domain

#### [MODIFY] domains/app/api/endpoints.py
- Modify `market_websocket` to subscribe to `market.options_updated.{symbol}`.

### 4. Infrastructure/Scripts

#### [MODIFY] scripts/entrypoint_single_container.sh
- Launch `options_subscriber` as background daemon.

## Verification Plan

### Automated Tests
1. Unit test `CrankNicolsonPDE` by manually calling it with known dummy values in a script and checking boundaries.
2. Ensure redis streams are publishing and consuming messages correctly.

### Manual Verification
1. Run server `docker compose up` or standard startup scripts.
2. Trigger the ingestion celery task manually or via `celery beat`.
3. Open websocket connection to verify ephemeral events stream real-time JSON for the computed fair options prices.
