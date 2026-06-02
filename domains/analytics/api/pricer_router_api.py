"""
File Overview: FastAPI router for options pricer BSM calculations and ticker mock/real data queries.

All Functions/Classes:
- pricer_router: APIRouter for pricer services.
- get_ticker_parameters: GET endpoint fetching real-time Redis or deterministic mock options parameters for a symbol.
- calculate_bsm: POST endpoint executing BSM pricer and returning intermediate / final option edge parameters.
"""
import math
import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np
from scipy.stats import norm
from fastapi import APIRouter, HTTPException

from shared.utils.symbol_validator import SymbolValidator
from shared.infrastructure.redis_client import get_redis_client
from shared.constants import RedisKeys
from domains.analytics.api.schemas import (
    PricerTickerDataResponse,
    BSMCalculateRequest,
    BSMCalculateResponse,
    OptionChainRow,
    OptionChainSide,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pricer", tags=["pricer"])


def _generated_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_deterministic_mocks(symbol: str) -> dict:
    """Generate realistic, deterministic mocks based on hash of symbol."""
    h = int(hashlib.md5(symbol.encode()).hexdigest(), 16)
    
    # AAPL spec mock
    if symbol == "AAPL":
        return {
            "stock_price": 182.45,
            "implied_volatility": 28.4,
            "historical_volatility": 25.2,
            "bid_price": 6.70,
            "ask_price": 7.10, # bid 6.70, mid 6.90, ask 7.10 (midpoint midpoint)
            "open_interest": 14200,
            "volume": 5800,
            "strike_price": 185.00,
            "expiry_days": 60,
            "risk_free_rate": 5.25,
            "dividend_yield": 0.55,
        }
    # TSLA spec mock
    elif symbol == "TSLA":
        return {
            "stock_price": 177.40,
            "implied_volatility": 48.6,
            "historical_volatility": 44.5,
            "bid_price": 11.20,
            "ask_price": 11.80,
            "open_interest": 22400,
            "volume": 12800,
            "strike_price": 180.00,
            "expiry_days": 30,
            "risk_free_rate": 5.25,
            "dividend_yield": 0.0,
        }
    # NIFTY Index mock
    elif symbol == "NIFTY":
        return {
            "stock_price": 22450.00,
            "implied_volatility": 12.80,
            "historical_volatility": 11.50,
            "bid_price": 155.20,
            "ask_price": 157.60,
            "open_interest": 85000,
            "volume": 142000,
            "strike_price": 22500.00,
            "expiry_days": 5,
            "risk_free_rate": 6.50,
            "dividend_yield": 1.20,
        }

    # Deterministic general formula
    base_price = 100.0 + (h % 300)  # $100 - $400
    iv = 15.0 + (h % 45)  # 15% - 60%
    hv = iv * 0.9
    bid = base_price * 0.05
    ask = bid * 1.05

    return {
        "stock_price": round(base_price, 2),
        "implied_volatility": round(iv, 2),
        "historical_volatility": round(hv, 2),
        "bid_price": round(bid, 2),
        "ask_price": round(ask, 2),
        "open_interest": int(1000 + (h % 15000)),
        "volume": int(100 + (h % 4000)),
        "strike_price": round(base_price * 1.02, 2),
        "expiry_days": int(10 + (h % 80)),
        "risk_free_rate": 5.25,
        "dividend_yield": 0.50,
    }


def bsm_price(S, K, T_days, r, q, iv_pct, option_type):
    T_years = max(T_days, 0.001) / 365.0
    r_frac = r / 100.0
    q_frac = q / 100.0
    sigma_frac = iv_pct / 100.0
    
    try:
        d1 = (math.log(S / K) + (r_frac - q_frac + 0.5 * sigma_frac ** 2) * T_years) / (sigma_frac * math.sqrt(T_years))
        d2 = d1 - sigma_frac * math.sqrt(T_years)
        
        if option_type == "call":
            val = S * math.exp(-q_frac * T_years) * norm.cdf(d1) - K * math.exp(-r_frac * T_years) * norm.cdf(d2)
        else:
            val = K * math.exp(-r_frac * T_years) * norm.cdf(-d2) - S * math.exp(-q_frac * T_years) * norm.cdf(-d1)
        return max(val, 0.01)
    except Exception:
        return 0.01


def _get_mock_expiry_dates() -> list[str]:
    today = datetime.now(timezone.utc).date()
    expiries = []
    days_ahead = 3 - today.weekday()
    if days_ahead < 0:
        days_ahead += 7
    if days_ahead == 0:
        days_ahead = 7
    next_thurs = today + timedelta(days=days_ahead)
    expiries.append(next_thurs.isoformat())
    for i in range(1, 4):
        expiries.append((next_thurs + timedelta(weeks=i)).isoformat())
    return expiries


def _generate_mock_option_chain(
    symbol: str,
    stock_price: float,
    implied_volatility: float,
    risk_free_rate: float,
    dividend_yield: float,
    open_interest: int,
    volume: int,
    expiry_dates: list[str]
) -> dict[str, list[OptionChainRow]]:
    option_chains = {}
    is_index = symbol.upper() in {"NIFTY"} or "INDEX" in symbol.upper() or stock_price > 5000
    spacing = 50.0 if is_index else 10.0
    atm_strike = round(stock_price / spacing) * spacing
    today = datetime.now(timezone.utc).date()
    
    for exp_date in expiry_dates:
        try:
            exp_dt = datetime.strptime(exp_date, "%Y-%m-%d").date()
            T_days = max((exp_dt - today).days, 1)
        except Exception:
            T_days = 30
            
        rows = []
        for i in range(-20, 21):
            strike = float(atm_strike + i * spacing)
            if strike <= 0:
                continue
                
            d = (strike - stock_price) / stock_price
            iv_smile = implied_volatility * (1.0 + 1.5 * (d ** 2))
            
            call_ltp = bsm_price(stock_price, strike, T_days, risk_free_rate, dividend_yield, iv_smile, "call")
            put_ltp = bsm_price(stock_price, strike, T_days, risk_free_rate, dividend_yield, iv_smile, "put")
            
            call_spread = max(0.05, call_ltp * 0.02)
            put_spread = max(0.05, put_ltp * 0.02)
            
            call_bid = max(0.05, round(call_ltp - call_spread / 2, 2))
            call_ask = max(0.05, round(call_ltp + call_spread / 2, 2))
            put_bid = max(0.05, round(put_ltp - put_spread / 2, 2))
            put_ask = max(0.05, round(put_ltp + put_spread / 2, 2))
            
            strike_hash = int(hashlib.md5(f"{symbol}-{exp_date}-{strike}".encode()).hexdigest(), 16)
            
            call_bid_qty = int(100 + (strike_hash % 20) * 50) * (2 if abs(d) < 0.05 else 1)
            call_ask_qty = int(((strike_hash >> 1) % 20) * 50 + 100) * (2 if abs(d) < 0.05 else 1)
            put_bid_qty = int(((strike_hash >> 2) % 20) * 50 + 100) * (2 if abs(d) < 0.05 else 1)
            put_ask_qty = int(((strike_hash >> 3) % 20) * 50 + 100) * (2 if abs(d) < 0.05 else 1)
            
            factor = math.exp(-25.0 * (d ** 2))
            call_oi = int(open_interest * factor * (1.2 if strike > stock_price else 0.8))
            put_oi = int(open_interest * factor * (1.2 if strike < stock_price else 0.8))
            
            call_volume = int(volume * factor * (1.1 if strike > stock_price else 0.9))
            put_volume = int(volume * factor * (1.1 if strike < stock_price else 0.9))
            
            noise_call_oi = 0.8 + 0.4 * ((strike_hash % 100) / 100.0)
            noise_call_vol = 0.8 + 0.4 * (((strike_hash >> 4) % 100) / 100.0)
            noise_put_oi = 0.8 + 0.4 * (((strike_hash >> 8) % 100) / 100.0)
            noise_put_vol = 0.8 + 0.4 * (((strike_hash >> 12) % 100) / 100.0)
            
            call_oi = int(call_oi * noise_call_oi)
            call_volume = int(call_volume * noise_call_vol)
            put_oi = int(put_oi * noise_put_oi)
            put_volume = int(put_volume * noise_put_vol)
            
            call_chng_in_oi = int(call_oi * 0.1 * (((strike_hash >> 16) % 200 - 100) / 100.0))
            put_chng_in_oi = int(put_oi * 0.1 * (((strike_hash >> 20) % 200 - 100) / 100.0))
            
            call_chng = round(call_ltp * 0.05 * (((strike_hash >> 24) % 200 - 100) / 100.0), 2)
            put_chng = round(put_ltp * 0.05 * (((strike_hash >> 28) % 200 - 100) / 100.0), 2)
            
            rows.append(OptionChainRow(
                strike_price=strike,
                call=OptionChainSide(
                    oi=max(call_oi, 0),
                    chng_in_oi=call_chng_in_oi,
                    volume=max(call_volume, 0),
                    iv=round(iv_smile, 2),
                    ltp=round(call_ltp, 2),
                    chng=call_chng,
                    bid_qty=call_bid_qty,
                    bid=call_bid,
                    ask=call_ask,
                    ask_qty=call_ask_qty
                ),
                put=OptionChainSide(
                    oi=max(put_oi, 0),
                    chng_in_oi=put_chng_in_oi,
                    volume=max(put_volume, 0),
                    iv=round(iv_smile, 2),
                    ltp=round(put_ltp, 2),
                    chng=put_chng,
                    bid_qty=put_bid_qty,
                    bid=put_bid,
                    ask=put_ask,
                    ask_qty=put_ask_qty
                )
            ))
            
        option_chains[exp_date] = rows
        
    return option_chains



@router.get("/ticker/{symbol}", response_model=PricerTickerDataResponse)
async def get_ticker_parameters(symbol: str):
    """
    Get live or mock options pricing parameters for the BSM Pricer inputs.
    Tries to read live options chain cache from Redis first.
    """
    symbol_upper = symbol.strip().upper()
    # Basic format check: must be alphanumeric (allowing dot, hyphen, caret)
    clean_format = symbol_upper.replace(".", "").replace("-", "").replace("^", "")
    if not clean_format or not clean_format.isalnum():
        raise HTTPException(
            status_code=400,
            detail=f"Symbol '{symbol_upper}' is invalid or not supported."
        )

    import asyncio
    symbol_clean = await asyncio.get_running_loop().run_in_executor(
        None, SymbolValidator.get_clean_symbol, symbol_upper
    )
    
    raw_cached = None
    price_cached = None
    redis = None
    try:
        redis = await get_redis_client()
        # Attempt to load options cache
        raw_key = RedisKeys.MARKET_OPTIONS.format(symbol=symbol_clean)
        raw_cached = await redis.get(raw_key)

        # Attempt to load spot price cache
        price_key = RedisKeys.MARKET_PRICE.format(symbol=symbol_clean)
        price_cached = await redis.get(price_key)
    except Exception as exc:
        logger.warning("[%s] Failed connecting to Redis, falling back to mocks: %s", symbol_clean, exc)

    if not raw_cached:
        # Try live fetch
        from domains.ingestion.infrastructure.adapters.outbound.nse_api_adapter import NseApiAdapter
        adapter = NseApiAdapter()
        dtos = []
        live_price_data = None
        try:
            dtos = await adapter.fetch_option_chain(symbol_clean)
            live_price_data = await adapter.fetch_price(symbol_clean)
        except Exception as fetch_exc:
            logger.error("[%s] Dynamic live fetch failed: %s", symbol_clean, fetch_exc)
        finally:
            await adapter.close()

        if dtos:
            spot_price = dtos[0].underlying_price
            if spot_price <= 0 and live_price_data:
                spot_price = float(live_price_data.get("last_price", 0.0))
            
            chains = {}
            expiry_dates = set()
            for dto in dtos:
                if not dto.expiry:
                    continue
                expiry_dates.add(dto.expiry)
                if dto.expiry not in chains:
                    chains[dto.expiry] = []
                chains[dto.expiry].append({
                    "strike": dto.strike,
                    "type": dto.option_type,
                    "last_price": dto.ltp,
                    "oi": dto.oi,
                    "volume": dto.volume,
                    "iv": dto.iv,
                    "expiry": dto.expiry
                })
            
            data = {
                "symbol": symbol_clean,
                "spot_price": spot_price,
                "expiry_dates": sorted(list(expiry_dates)),
                "chains": chains,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "summary": {"total_strikes": len(set(d.strike for d in dtos))}
            }
            
            if redis:
                try:
                    raw_key = RedisKeys.MARKET_OPTIONS.format(symbol=symbol_clean)
                    await redis.set(raw_key, json.dumps(data, default=str), ex=600)
                    
                    price_key = RedisKeys.MARKET_PRICE.format(symbol=symbol_clean)
                    p_data = {
                        "symbol": symbol_clean,
                        "last_price": spot_price,
                        "last_updated": datetime.now(timezone.utc).date().isoformat()
                    }
                    await redis.set(price_key, json.dumps(p_data, default=str), ex=600)
                except Exception as cache_exc:
                    logger.warning("[%s] Failed caching dynamically fetched options to Redis: %s", symbol_clean, cache_exc)
            
            raw_cached = json.dumps(data, default=str)
        elif live_price_data:
            spot_price = float(live_price_data.get("last_price", 0.0))
            data = {
                "symbol": symbol_clean,
                "spot_price": spot_price,
                "expiry_dates": [],
                "chains": {},
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "summary": {"total_strikes": 0}
            }
            if redis:
                try:
                    raw_key = RedisKeys.MARKET_OPTIONS.format(symbol=symbol_clean)
                    await redis.set(raw_key, json.dumps(data, default=str), ex=600)
                    
                    price_key = RedisKeys.MARKET_PRICE.format(symbol=symbol_clean)
                    p_data = {
                        "symbol": symbol_clean,
                        "last_price": spot_price,
                        "last_updated": datetime.now(timezone.utc).date().isoformat()
                    }
                    await redis.set(price_key, json.dumps(p_data, default=str), ex=600)
                except Exception as cache_exc:
                    logger.warning("[%s] Failed caching empty options to Redis: %s", symbol_clean, cache_exc)
            
            raw_cached = json.dumps(data, default=str)
        else:
            data = {
                "symbol": symbol_clean,
                "spot_price": 0.0,
                "expiry_dates": [],
                "chains": {},
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "summary": {"total_strikes": 0}
            }
            raw_cached = json.dumps(data, default=str)

    if raw_cached:
        try:
            chain_data = json.loads(raw_cached)
            spot = float(chain_data.get("spot_price", 0.0))
            if spot <= 0 and price_cached:
                p_data = json.loads(price_cached)
                spot = float(p_data.get("last_price", 0.0))

            expiries = chain_data.get("expiry_dates", [])
            chains = chain_data.get("chains", {})

            if not expiries or not chains:
                return PricerTickerDataResponse(
                    symbol=symbol_clean,
                    stock_price=spot,
                    implied_volatility=0.0,
                    historical_volatility=0.0,
                    bid_price=0.0,
                    ask_price=0.0,
                    open_interest=0,
                    volume=0,
                    strike_price=0.0,
                    expiry_days=0,
                    risk_free_rate=6.5 if "NS" in symbol_upper or symbol_clean in {"NIFTY"} else 5.25,
                    dividend_yield=0.0,
                    expiry_dates=[],
                    option_chains={},
                    generated_at=_generated_at(),
                    source="live_market_fetch" if spot > 0 else "deterministic_mock",
                    stale=False,
                    partial=False,
                    status="COMPLETED",
                )

            if spot > 0 and expiries and chains:
                # Target nearest expiry
                nearest_exp = expiries[0]
                strikes_data = chains.get(nearest_exp, [])

                # Find near-the-money call option
                nearest_strike_opt = None
                min_diff = float("inf")
                for opt in strikes_data:
                    diff = abs(opt["strike"] - spot)
                    if diff < min_diff:
                        min_diff = diff
                        nearest_strike_opt = opt

                if nearest_strike_opt:
                    # Calculate implied/historical params
                    # Expiry days estimation
                    try:
                        exp_dt = datetime.strptime(nearest_exp, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                        delta = (exp_dt - datetime.now(timezone.utc)).days
                        expiry_days = max(delta, 1)
                    except Exception:
                        expiry_days = 30

                    ltp = float(nearest_strike_opt.get("last_price", 0.0))
                    bid = round(ltp * 0.98, 2)
                    ask = round(ltp * 1.02, 2)
                    iv = float(nearest_strike_opt.get("iv", 0.0) or 0.0)
                    if iv > 0.0 and iv < 1.0:
                        iv *= 100.0
                    elif iv <= 0:
                        iv = 25.0

                    # Parse option chains for ALL expiries from Redis
                    option_chains = {}
                    for exp_date in expiries:
                        exp_strikes = chains.get(exp_date, [])
                        rows_by_strike = {}
                        for opt in exp_strikes:
                            strike = float(opt["strike"])
                            if strike not in rows_by_strike:
                                rows_by_strike[strike] = {
                                    "strike_price": strike,
                                    "call": {"oi": 0, "chng_in_oi": 0, "volume": 0, "iv": 0.0, "ltp": 0.0, "chng": 0.0, "bid_qty": 0, "bid": 0.0, "ask": 0.0, "ask_qty": 0},
                                    "put": {"oi": 0, "chng_in_oi": 0, "volume": 0, "iv": 0.0, "ltp": 0.0, "chng": 0.0, "bid_qty": 0, "bid": 0.0, "ask": 0.0, "ask_qty": 0}
                                }
                            opt_type = opt.get("type", "").upper()
                            side = "call" if opt_type in ("CE", "CALL") else "put"
                            
                            iv_val = float(opt.get("iv", 0.0) or 0.0)
                            if iv_val > 0.0 and iv_val < 1.0:
                                iv_val *= 100.0
                            elif iv_val <= 0:
                                iv_val = iv
                                
                            ltp_val = float(opt.get("last_price", 0.0) or 0.0)
                            
                            b_val = float(opt.get("bid", 0.0) or 0.0)
                            a_val = float(opt.get("ask", 0.0) or 0.0)
                            if b_val <= 0 or a_val <= 0:
                                spread_val = max(0.05, ltp_val * 0.02)
                                b_val = round(ltp_val - spread_val / 2, 2)
                                a_val = round(ltp_val + spread_val / 2, 2)
                                
                            rows_by_strike[strike][side] = {
                                "oi": int(opt.get("oi", 0) or 0),
                                "chng_in_oi": int(opt.get("chng_in_oi", 0) or 0),
                                "volume": int(opt.get("volume", 0) or 0),
                                "iv": iv_val,
                                "ltp": ltp_val,
                                "chng": float(opt.get("change", 0.0) or 0.0),
                                "bid_qty": int(opt.get("bid_qty", 0) or 100),
                                "bid": b_val,
                                "ask": a_val,
                                "ask_qty": int(opt.get("ask_qty", 0) or 100)
                            }
                            
                        sorted_rows = []
                        for strike in sorted(rows_by_strike.keys()):
                            sorted_rows.append(OptionChainRow(
                                strike_price=strike,
                                call=OptionChainSide(**rows_by_strike[strike]["call"]),
                                put=OptionChainSide(**rows_by_strike[strike]["put"])
                            ))
                        option_chains[exp_date] = sorted_rows

                    return PricerTickerDataResponse(
                        symbol=symbol_clean,
                        stock_price=spot,
                        implied_volatility=iv,
                        historical_volatility=round(iv * 0.88, 2),
                        bid_price=bid,
                        ask_price=ask,
                        open_interest=int(nearest_strike_opt.get("oi", 1000)),
                        volume=int(nearest_strike_opt.get("volume", 200)),
                        strike_price=float(nearest_strike_opt.get("strike", spot)),
                        expiry_days=expiry_days,
                        risk_free_rate=6.5 if "NS" in symbol_upper or symbol_clean in {"NIFTY"} else 5.25,
                        dividend_yield=0.5,
                        expiry_dates=expiries,
                        option_chains=option_chains,
                        generated_at=_generated_at(),
                        source="redis_cache",
                        stale=False,
                        partial=False,
                        status="COMPLETED",
                    )
        except Exception as exc:
            logger.warning("[%s] Failed fetching real-time pricer options params from Redis: %s", symbol_clean, exc)

    # Fallback to deterministic clean mock parameters
    mocks = _get_deterministic_mocks(symbol_clean)
    expiry_dates = _get_mock_expiry_dates()
    option_chains = _generate_mock_option_chain(
        symbol_clean,
        mocks["stock_price"],
        mocks["implied_volatility"],
        mocks["risk_free_rate"],
        mocks["dividend_yield"],
        mocks["open_interest"],
        mocks["volume"],
        expiry_dates
    )
    return PricerTickerDataResponse(
        symbol=symbol_clean,
        stock_price=mocks["stock_price"],
        implied_volatility=mocks["implied_volatility"],
        historical_volatility=mocks["historical_volatility"],
        bid_price=mocks["bid_price"],
        ask_price=mocks["ask_price"],
        open_interest=mocks["open_interest"],
        volume=mocks["volume"],
        strike_price=mocks["strike_price"],
        expiry_days=mocks["expiry_days"],
        risk_free_rate=mocks["risk_free_rate"],
        dividend_yield=mocks["dividend_yield"],
        expiry_dates=expiry_dates,
        option_chains=option_chains,
        generated_at=_generated_at(),
        source="deterministic_mock",
        stale=True,
        partial=False,
        status="COMPLETED",
    )


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
