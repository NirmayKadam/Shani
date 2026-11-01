"""
File Overview: FastAPI router for derivatives-related analytics endpoints.

All Functions/Classes:
- get_derivatives: FastAPI GET endpoint. Take symbol from path and send placeholder response.

Endpoints/APIs:
- GET /v1/derivatives/{symbol}.

Database Tables:
- None.
"""
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException

from shared.utils.symbol_validator import SymbolValidator
from shared.infrastructure.redis_client import get_redis_client
from shared.constants import RedisKeys, TTL
from domains.analytics.application.dto.read_models_dto import compute_pcr
from domains.analytics.api.schemas import DerivativesResponse, PricedStrike, TechnicalsResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/derivatives", tags=["derivatives"])


def _generated_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def _error_envelope(*, error: str, code: str, details=None) -> dict:
    return {
        "generated_at": _generated_at(),
        "source": "frontend_api",
        "stale": True,
        "partial": True,
        "error": error,
        "code": code,
        "details": details,
    }


@router.get("/{symbol}", response_model=DerivativesResponse)
async def get_derivatives(symbol: str):
    """
    Get options and Crank-Nicolson priced derivatives for a given symbol.
    Cache-first and decoupled.
    """
    symbol_upper = symbol.strip().upper()

    is_valid = await asyncio.to_thread(SymbolValidator.validate, symbol_upper)
    if not is_valid:
        raise HTTPException(
            status_code=400,
            detail=_error_envelope(
                error=f"Symbol '{symbol_upper}' is invalid or not supported.",
                code="invalid_symbol",
                details={
                    "hint": "Ensure the ticker is correct (e.g., RELIANCE or AAPL). Use .NS suffix for Indian stocks if needed.",
                },
            ),
        )

    symbol_clean = await asyncio.to_thread(SymbolValidator.get_clean_symbol, symbol_upper)
    redis = await get_redis_client()

    # 1. Fetch raw option chain statistics
    raw_key = RedisKeys.MARKET_OPTIONS.format(symbol=symbol_clean)
    raw_cached = await redis.get(raw_key)

    pcr = None
    ce_volume = 0
    pe_volume = 0
    ce_oi = 0
    pe_oi = 0
    total_strikes = 0
    expiry_dates = []
    last_updated = ""
    available = False

    if raw_cached:
        try:
            option_chain = json.loads(raw_cached)
            pcr_data = compute_pcr(option_chain)

            pcr = pcr_data.get("pcr")
            ce_volume = int(pcr_data.get("ce_volume", 0))
            pe_volume = int(pcr_data.get("pe_volume", 0))
            ce_oi = int(pcr_data.get("ce_oi", 0))
            pe_oi = int(pcr_data.get("pe_oi", 0))
            total_strikes = int(option_chain.get("summary", {}).get("total_strikes", 0))
            expiry_dates = option_chain.get("expiry_dates", [])
            last_updated = option_chain.get("fetched_at", "")
            available = True
        except Exception as exc:
            logger.warning("[%s] Failed parsing raw options chain snapshot: %s", symbol_clean, exc)

    # 2. Fetch Crank-Nicolson PDE priced options chain
    priced_key = RedisKeys.MARKET_OPTIONS_PRICED.format(symbol=symbol_clean)
    priced_cached = await redis.get(priced_key)

    fair_priced_chain = []
    priced_last_updated = ""

    if priced_cached:
        try:
            priced_payload = json.loads(priced_cached)
            priced_chain_raw = priced_payload.get("chain", [])
            priced_last_updated = priced_payload.get("last_updated", "")
            
            optional_fields = ("fair_call", "fair_put", "call_iv", "put_iv",
                               "bs_fair_call", "bs_fair_put", "live_call", "live_put")
            for item in priced_chain_raw:
                fair_priced_chain.append(PricedStrike(
                    strike=float(item.get("strike", 0.0)),
                    **{f: float(item[f]) if item.get(f) is not None else None for f in optional_fields},
                ))
        except Exception as exc:
            logger.warning("[%s] Failed parsing priced option chain snapshot: %s", symbol_clean, exc)

    # Freshness: the cache keys expire after 60-120 s, so with no data there is nothing fresh to
    # report (stale) and no timestamp to show. Otherwise compare against the priced-chain TTL.
    stale = True
    effective_last_updated = priced_last_updated or last_updated
    if effective_last_updated:
        try:
            dt = datetime.fromisoformat(effective_last_updated.replace("Z", "+00:00"))
            age_seconds = (datetime.now(timezone.utc) - dt).total_seconds()
            stale = age_seconds > TTL.MARKET_OPTIONS_PRICED
        except Exception:
            pass

    return DerivativesResponse(
        symbol=symbol_clean,
        pcr=pcr,
        ce_volume=ce_volume,
        pe_volume=pe_volume,
        ce_oi=ce_oi,
        pe_oi=pe_oi,
        total_strikes=total_strikes,
        expiry_dates=expiry_dates,
        fair_priced_chain=fair_priced_chain,
        available=available and len(fair_priced_chain) > 0,
        last_updated=effective_last_updated,
        generated_at=_generated_at(),
        source="redis_read_model",
        stale=stale,
        partial=not (available and len(fair_priced_chain) > 0),
        status="COMPLETED" if (available and len(fair_priced_chain) > 0) else "CALCULATING"
    )


async def _daily_history(symbol_clean: str):
    """3 months of daily (closes, highs, lows) from yfinance, cached in Redis for an hour.

    Daily bars change once a day, so refetching them on every dashboard refresh only adds latency
    and yfinance rate-limit risk. Failures and empty results are not cached.
    """
    cache_key = RedisKeys.HISTORY_DAILY_3MO.format(symbol=symbol_clean)
    redis = None
    try:
        redis = await get_redis_client()
        cached = await redis.get(cache_key)
        if cached:
            data = json.loads(cached)
            return data["closes"], data.get("highs"), data.get("lows")
    except Exception as exc:
        logger.warning("History cache read failed for %s: %s", symbol_clean, exc)

    try:
        from domains.ingestion.infrastructure.outbound.nse_api_adapter import _to_yfinance_symbol
        import yfinance as yf

        yf_symbol = _to_yfinance_symbol(symbol_clean)

        def _fetch_hist():
            hist = yf.Ticker(yf_symbol).history(period="3mo")
            if hist.empty or "Close" not in hist:
                return [], None, None
            hist = hist.dropna(subset=["Close"])
            if {"High", "Low"} <= set(hist.columns):
                hist = hist.dropna(subset=["High", "Low"])
                return hist["Close"].tolist(), hist["High"].tolist(), hist["Low"].tolist()
            return hist["Close"].tolist(), None, None

        closes, highs, lows = await asyncio.to_thread(_fetch_hist)
    except Exception as hist_exc:
        logger.warning("Failed fetching historical prices for %s technicals: %s", symbol_clean, hist_exc)
        return [], None, None

    if closes and redis is not None:
        try:
            await redis.set(cache_key, json.dumps({"closes": closes, "highs": highs, "lows": lows}),
                            ex=TTL.HISTORICAL_OHLC)
        except Exception as exc:
            logger.warning("History cache write failed for %s: %s", symbol_clean, exc)
    return closes, highs, lows


@router.get("/{symbol}/technicals", response_model=TechnicalsResponse)
async def get_technicals(symbol: str, spot: Optional[float] = None):
    """
    Get calculated technical indicators and color-coded signals for symbol.
    """
    from domains.analytics.application.technicals_calculator import compute_all_technicals

    symbol_upper = symbol.strip().upper()
    symbol_clean = await asyncio.to_thread(SymbolValidator.get_clean_symbol, symbol_upper)

    # Prefer the cached chain's spot (the snapshot field is spot_price); ?spot is the fallback.
    spot_price = spot if spot is not None and spot > 0 else None
    try:
        redis = await get_redis_client()
        raw_cached = await redis.get(RedisKeys.MARKET_OPTIONS.format(symbol=symbol_clean))
        if raw_cached:
            cached_spot = float(json.loads(raw_cached).get("spot_price") or 0.0)
            if cached_spot > 0:
                spot_price = cached_spot
    except Exception as exc:
        logger.warning("Redis fetch error in technicals for %s: %s", symbol_clean, exc)

    if spot_price is None:
        raise HTTPException(
            status_code=422,
            detail=f"Spot price is required for technicals calculation of '{symbol_upper}'. Pass ?spot=<price> or ensure Redis has cached data."
        )

    closes, highs, lows = await _daily_history(symbol_clean)

    technicals_data = compute_all_technicals(spot_price, price_history=closes, highs=highs, lows=lows)
    technicals_data["symbol"] = symbol_clean
    technicals_data["generated_at"] = _generated_at()
    technicals_data["source"] = "analytics_domain_engine"
    technicals_data["stale"] = False
    technicals_data["partial"] = False
    technicals_data["status"] = "COMPLETED"

    return technicals_data


