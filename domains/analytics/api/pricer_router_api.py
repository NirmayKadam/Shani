"""
File Overview: FastAPI router for options pricer BSM calculations and live ticker data queries.

All Functions/Classes:
- pricer_router: APIRouter for pricer services.
- get_ticker_parameters: GET endpoint fetching real-time Redis or dynamic live options parameters for a symbol.
- calculate_bsm: POST endpoint executing BSM pricer and returning intermediate / final option edge parameters.
"""
import asyncio
import math
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from scipy.stats import norm
from fastapi import APIRouter, HTTPException

from shared.utils.symbol_validator import SymbolValidator
from shared.utils.market_time import nearest_expiry, years_to_expiry, risk_free_rate_for
from shared.infrastructure.redis_client import get_redis_client
from shared.constants import RedisKeys, TTL
from domains.analytics.api.schemas import (
    PricerTickerDataResponse,
    BSMCalculateRequest,
    BSMCalculateResponse,
    OptionChainRow,
    OptionChainSide,
)
from domains.analytics.domain.services.bsm_calculator import BsmCalculatorDomainService


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pricer", tags=["pricer"])

# Letters, digits and the punctuation real tickers use: RELIANCE.NS, ^NSEI, BRK-B, M&M
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9.\-^&]+$")
# A chain snapshot older than this is reported as stale
_STALE_AFTER_SECONDS = 120
_HV_TTL_SECONDS = 3600
_HV_CACHE: dict[str, tuple[float, float]] = {}


def _generated_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def _historical_volatility_sync(symbol_clean: str) -> Optional[float]:
    """Annualised 30-day historical volatility in percent, or None if it cannot be computed."""
    try:
        import yfinance as yf
        from domains.ingestion.infrastructure.outbound.nse_api_adapter import _to_yfinance_symbol

        hist = yf.Ticker(_to_yfinance_symbol(symbol_clean)).history(period="1mo")
        if hist is None or len(hist) <= 5:
            return None
        log_returns = np.log(hist["Close"] / hist["Close"].shift(1)).dropna()
        hv = float(log_returns.std() * np.sqrt(252) * 100.0)
        return None if np.isnan(hv) else round(hv, 2)
    except Exception as exc:
        logger.debug("[%s] Historical volatility unavailable: %s", symbol_clean, exc)
        return None


async def _get_historical_volatility(symbol_clean: str) -> float:
    """TTL-cached historical volatility; failures are not cached, so a blip doesn't pin HV at 0."""
    cached = _HV_CACHE.get(symbol_clean)
    if cached and time.monotonic() - cached[1] < _HV_TTL_SECONDS:
        return cached[0]
    hv = await asyncio.to_thread(_historical_volatility_sync, symbol_clean)
    if hv is None:
        return 0.0
    _HV_CACHE[symbol_clean] = (hv, time.monotonic())
    return hv


async def _live_fetch(symbol_clean: str, redis) -> Optional[tuple[dict, Optional[dict]]]:
    """Fetch chain + quote from the market adapter and cache them. Returns (chain, price) or None."""
    from domains.ingestion.infrastructure.outbound.adapter_factory import get_market_data_adapter
    from domains.ingestion.application.services.ingestion_service import build_option_chain_snapshot

    adapter = get_market_data_adapter()
    dtos, price_data = [], None
    try:
        dtos = await adapter.fetch_option_chain(symbol_clean)
        price_data = await adapter.fetch_price(symbol_clean)
    except Exception as fetch_exc:
        logger.error("[%s] Dynamic live fetch failed: %s", symbol_clean, fetch_exc)
    finally:
        await adapter.close()

    if dtos:
        chain = build_option_chain_snapshot(symbol_clean, dtos)
    elif price_data:
        chain = {
            "symbol": symbol_clean, "spot_price": 0.0, "expiry_dates": [], "chains": {},
            "fetched_at": _generated_at(), "summary": {"total_strikes": 0},
        }
    else:
        return None

    if chain["spot_price"] <= 0 and price_data:
        chain["spot_price"] = float(price_data.get("last_price", 0.0))

    if redis:
        try:
            await redis.set(RedisKeys.MARKET_OPTIONS.format(symbol=symbol_clean),
                            json.dumps(chain, default=str), ex=TTL.MARKET_OPTIONS)
            if price_data:
                await redis.set(RedisKeys.MARKET_PRICE.format(symbol=symbol_clean),
                                json.dumps(price_data, default=str), ex=TTL.MARKET_PRICE)
        except Exception as cache_exc:
            logger.warning("[%s] Failed caching live-fetched market data: %s", symbol_clean, cache_exc)
    return chain, price_data


def _atm_call(strikes_data: list, spot: float) -> Optional[dict]:
    """Call row with the strike nearest spot (puts are excluded: the headline IV is a call IV)."""
    calls = [o for o in strikes_data if str(o.get("type", "")).upper() in ("CE", "CALL")]
    return min(calls, key=lambda o: abs(float(o["strike"]) - spot)) if calls else None


def _iv_percent(iv) -> float:
    """Adapters emit IV as a decimal (0.142); the pricer API reports percent (14.2)."""
    iv = float(iv or 0.0)
    return round(iv * 100.0, 4) if iv > 0 else 0.0


def _chain_rows(chains: dict, expiries: list) -> dict[str, list[OptionChainRow]]:
    empty_side = {"oi": 0, "chng_in_oi": 0, "volume": 0, "iv": 0.0, "ltp": 0.0, "chng": 0.0,
                  "bid_qty": None, "bid": None, "ask": None, "ask_qty": None}
    option_chains = {}
    for exp_date in expiries:
        rows_by_strike: dict[float, dict] = {}
        for opt in chains.get(exp_date, []):
            strike = float(opt["strike"])
            row = rows_by_strike.setdefault(
                strike, {"call": dict(empty_side), "put": dict(empty_side)}
            )
            side = "call" if str(opt.get("type", "")).upper() in ("CE", "CALL") else "put"
            bid = float(opt.get("bid", 0.0) or 0.0)
            ask = float(opt.get("ask", 0.0) or 0.0)
            bid_qty = int(opt.get("bid_qty", 0) or 0)
            ask_qty = int(opt.get("ask_qty", 0) or 0)
            row[side] = {
                "oi": int(opt.get("oi", 0) or 0),
                "chng_in_oi": int(opt.get("chng_in_oi", 0) or 0),
                "volume": int(opt.get("volume", 0) or 0),
                "iv": _iv_percent(opt.get("iv")),
                "ltp": float(opt.get("last_price", 0.0) or 0.0),
                "chng": float(opt.get("change", 0.0) or 0.0),
                "bid_qty": bid_qty or None,
                "bid": bid or None,
                "ask": ask or None,
                "ask_qty": ask_qty or None,
            }
        option_chains[exp_date] = [
            OptionChainRow(
                strike_price=strike,
                call=OptionChainSide(**rows_by_strike[strike]["call"]),
                put=OptionChainSide(**rows_by_strike[strike]["put"]),
            )
            for strike in sorted(rows_by_strike)
        ]
    return option_chains


def _is_stale(fetched_at: str) -> bool:
    try:
        fetched = datetime.fromisoformat(str(fetched_at).replace("Z", "+00:00"))
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - fetched).total_seconds() > _STALE_AFTER_SECONDS
    except (TypeError, ValueError):
        return True


@router.get("/ticker/{symbol}", response_model=PricerTickerDataResponse)
async def get_ticker_parameters(symbol: str):
    """
    Get live options pricing parameters for the BSM Pricer inputs.
    Reads the option chain snapshot from Redis, falling back to a live market fetch.
    """
    symbol_upper = symbol.strip().upper()
    if not _SYMBOL_PATTERN.match(symbol_upper):
        raise HTTPException(
            status_code=400,
            detail=f"Symbol '{symbol_upper}' is invalid or not supported."
        )

    symbol_clean = await asyncio.to_thread(SymbolValidator.get_clean_symbol, symbol_upper)
    rate = risk_free_rate_for(symbol_clean)

    raw_cached = price_cached = redis = None
    try:
        redis = await get_redis_client()
        raw_cached = await redis.get(RedisKeys.MARKET_OPTIONS.format(symbol=symbol_clean))
        price_cached = await redis.get(RedisKeys.MARKET_PRICE.format(symbol=symbol_clean))
    except Exception as exc:
        logger.warning("[%s] Failed connecting to Redis, falling back to direct adapter fetch: %s", symbol_clean, exc)

    source = "redis_cache"
    chain_data = json.loads(raw_cached) if raw_cached else None
    price_data = json.loads(price_cached) if price_cached else None
    if chain_data is None:
        fetched = await _live_fetch(symbol_clean, redis)
        if fetched is None:
            # Real market data unavailable across all sources (Groww, NSE, yfinance)
            raise HTTPException(
                status_code=503,
                detail=f"Live market data is currently unavailable for '{symbol_clean}' across all market sources."
            )
        chain_data, live_price = fetched
        price_data = live_price or price_data
        source = "live_market_fetch"

    try:
        spot = float(chain_data.get("spot_price", 0.0) or 0.0)
        if spot <= 0 and price_data:
            spot = float(price_data.get("last_price", 0.0) or 0.0)
        dividend_yield = float((price_data or {}).get("dividend_yield", 0.0) or 0.0)
        expiries = chain_data.get("expiry_dates", [])
        chains = chain_data.get("chains", {})
        stale = _is_stale(chain_data.get("fetched_at", ""))
        hv = await _get_historical_volatility(symbol_clean)

        common = dict(
            symbol=symbol_clean,
            stock_price=spot,
            data_as_of=str(chain_data.get("fetched_at", "") or ""),
            historical_volatility=hv,
            risk_free_rate=round(rate * 100.0, 4),
            dividend_yield=round(dividend_yield * 100.0, 4),
            generated_at=_generated_at(),
            source=source,
            stale=stale,
            partial=False,
            status="COMPLETED",
        )

        pricing_expiry = nearest_expiry(expiries) or (expiries[0] if expiries else None)
        atm = _atm_call(chains.get(pricing_expiry, []), spot) if (spot > 0 and pricing_expiry) else None
        if atm is None:
            if spot <= 0:
                raise HTTPException(
                    status_code=503,
                    detail=f"Live market data is currently unavailable for '{symbol_clean}' across all market sources."
                )
            # Quote available but no option chain: return the spot-only parameters
            return PricerTickerDataResponse(
                **common, implied_volatility=0.0, bid_price=None, ask_price=None,
                open_interest=0, volume=0, strike_price=0.0, expiry_days=0.0,
                expiry_dates=[], option_chains={},
            )

        T = years_to_expiry(pricing_expiry) or 30 / 365.0
        strike = float(atm["strike"])
        ltp = float(atm.get("last_price", 0.0) or 0.0)
        bid = float(atm.get("bid") or 0.0) or None
        ask = float(atm.get("ask") or 0.0) or None

        iv = _iv_percent(atm.get("iv"))
        if iv <= 0 and ltp > 0:
            solved = BsmCalculatorDomainService.solve_implied_volatility(
                market_price=ltp, spot=spot, strike=strike, expiry_years=T,
                rate=rate, option_type="call", dividend_yield=dividend_yield,
            )
            iv = round(solved * 100.0, 2) if solved and solved > 0 else 0.0

        return PricerTickerDataResponse(
            **common,
            implied_volatility=iv,
            bid_price=bid,
            ask_price=ask,
            open_interest=int(atm.get("oi", 0) or 0),
            volume=int(atm.get("volume", 0) or 0),
            strike_price=strike,
            expiry_days=round(T * 365.0, 2),
            expiry_dates=expiries,
            option_chains=_chain_rows(chains, expiries),
        )
    except HTTPException:
        raise
    except Exception:
        # A parsing bug is not "market data unavailable": log it and report an internal error.
        logger.exception("[%s] Failed building pricer parameters", symbol_clean)
        raise HTTPException(status_code=500, detail=f"Internal error building pricer parameters for '{symbol_clean}'.")


@router.post("/calculate", response_model=BSMCalculateResponse)
def calculate_bsm(request: BSMCalculateRequest):
    """
    Run high-precision Black-Scholes-Merton pricing logic on inputs.
    """
    S0 = request.S0
    K = request.K
    T_days = request.T_days
    r = request.r
    sigma = request.sigma
    option_type = request.option_type.strip().lower()
    q = request.q

    if S0 <= 0 or K <= 0 or T_days < 0 or sigma <= 0:
        raise HTTPException(
            status_code=422,
            detail="Stock price (S0), Strike (K), Expiry (T_days), and Volatility (sigma) must be greater than zero."
        )

    # Conversions
    T_years = max(T_days, 0.001) / 365.0
    r_frac = r / 100.0
    sigma_frac = sigma / 100.0
    q_frac = q / 100.0

    # Intermediate d1, d2 formulas
    try:
        d1 = (math.log(S0 / K) + (r_frac - q_frac + 0.5 * sigma_frac ** 2) * T_years) / (sigma_frac * math.sqrt(T_years))
        d2 = d1 - sigma_frac * math.sqrt(T_years)
    except ZeroDivisionError:
        raise HTTPException(status_code=422, detail="Volatility or Time to Expiry is too close to zero.")

    # Cumulative normal probabilities
    Nd1 = norm.cdf(d1)
    Nd2 = norm.cdf(d2)

    # Solvers
    if option_type == "call":
        fair_val = S0 * math.exp(-q_frac * T_years) * Nd1 - K * math.exp(-r_frac * T_years) * Nd2
    elif option_type == "put":
        fair_val = K * math.exp(-r_frac * T_years) * norm.cdf(-d2) - S0 * math.exp(-q_frac * T_years) * norm.cdf(-d1)
    else:
        raise HTTPException(
            status_code=400,
            detail="Option type must be 'call' or 'put'."
        )

    fair_val = max(fair_val, 0.0)

    # Edge computation
    edge = None
    if request.market_mid is not None and request.market_mid > 0:
        edge = fair_val - request.market_mid

    return BSMCalculateResponse(
        S0=S0,
        K=K,
        T_years=round(T_years, 4),
        r=r,
        sigma=sigma,
        option_type=option_type,
        q=q,
        d1=round(d1, 4),
        d2=round(d2, 4),
        Nd1=round(Nd1, 4),
        Nd2=round(Nd2, 4),
        fair_value=round(fair_val, 2),
        market_mid=request.market_mid,
        edge=round(edge, 2) if edge is not None else None,
    )
