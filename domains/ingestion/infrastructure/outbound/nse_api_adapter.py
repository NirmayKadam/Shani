"""
File Overview: Outbound adapter for NSE India and yfinance. Handles market price and option chain retrieval.

All Functions/Classes:
- MarketPriceFetcher: Price snapshot engine via NSE allIndices API and yfinance.
- OptionChainFetcher: Derivatives data engine via NSE V3 API using curl_cffi Chrome impersonation.
- NseApiAdapter: Port implementation for market data. Takes symbol and provides raw_tick_dto list and prices.

Endpoints/APIs: NSE India API, yfinance API

Database Tables: None
"""

import os
import math
import time
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from domains.ingestion.ports.interface.outbound.i_option_chain_source_port import IOptionChainSourcePort
from domains.ingestion.ports.interface.outbound.i_market_price_source_port import IMarketPriceSourcePort
from domains.ingestion.application.dto.raw_tick_dto import RawTickDTO

from curl_cffi.requests import AsyncSession
import yfinance as yf
import pytz

from shared.constants import MarketStatus, INDEX_SYMBOLS
from shared.utils.symbol_validator import SymbolValidator

logger = logging.getLogger(__name__)

# yfinance ticker.info cache per process: {yf_symbol: (monotonic_ts, q, currency)}
_INFO_CACHE: dict[str, tuple[float, float, str]] = {}
_INFO_CACHE_TTL_SECONDS = 24 * 3600

# ── NSE India API Configuration ────────────────────────────────

_NSE_BASE_URL = "https://www.nseindia.com"
_NSE_CONTRACT_INFO_URL = "https://www.nseindia.com/api/option-chain-contract-info?symbol={symbol}"
_NSE_OPTION_CHAIN_V3_URL = "https://www.nseindia.com/api/option-chain-v3?type={type}&symbol={symbol}&expiry={expiry}"
_NSE_ALL_INDICES_URL = "https://www.nseindia.com/api/allIndices"

_NSE_INDEX_NAME_MAP = {
    "NIFTY": "NIFTY 50",
    "BANKNIFTY": "NIFTY BANK",
    "FINNIFTY": "NIFTY FIN SERVICE",
    "MIDCPNIFTY": "NIFTY MIDCAP SELECT",
}

_NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

_NSE_API_HEADERS = {
    "User-Agent": _NSE_HEADERS["User-Agent"],
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/option-chain",
    "X-Requested-With": "XMLHttpRequest",
}

# ── Symbol Mapping for yfinance ─────────────────────────────────

_YFINANCE_SYMBOL_MAP = {
    "NIFTY": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "FINNIFTY": "^CNXFIN",
}


def _to_yfinance_symbol(symbol: str) -> str:
    """Convert watchlist symbol to yfinance ticker."""
    upper = symbol.upper()
    if upper in _YFINANCE_SYMBOL_MAP:
        return _YFINANCE_SYMBOL_MAP[upper]
    if "^" in upper or "." in upper:
        return upper
    return f"{upper}.NS"


def _get_market_status(now_dt: Optional[datetime] = None) -> MarketStatus:
    """Determine if Indian market (NSE) is currently open."""
    ist = pytz.timezone("Asia/Kolkata")
    if now_dt is not None:
        if now_dt.tzinfo is None:
            now = ist.localize(now_dt)
        else:
            now = now_dt.astimezone(ist)
    else:
        now = datetime.now(ist)

    if now.weekday() >= 5:
        return MarketStatus.CLOSED

    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

    if now < market_open:
        return MarketStatus.PRE_MARKET
    elif now > market_close:
        return MarketStatus.POST_MARKET
    else:
        return MarketStatus.OPEN


# ═══════════════════════════════════════════════════════════════
# Unified Market Data Adapter
# ═══════════════════════════════════════════════════════════════

class NseApiAdapter(IMarketPriceSourcePort, IOptionChainSourcePort):
    """
    Unified adapter for market data via NSE India (curl_cffi Chrome impersonation)
    and yfinance fallback.
    """

    def __init__(self) -> None:
        self._Session: Optional[AsyncSession] = None
        self._CookieRefreshTime: Optional[datetime] = None
        self._Loop: Optional[asyncio.AbstractEventLoop] = None
        self._Lock = asyncio.Lock()

    async def _ensure_session(self) -> AsyncSession:
        current_loop = asyncio.get_running_loop()
        if self._Session is not None and self._Loop is not current_loop:
            try:
                await self._Session.close()
            except Exception:
                pass
            self._Session = None
            self._CookieRefreshTime = None

        if self._Session is None:
            self._Session = AsyncSession(
                impersonate="chrome120",
                headers=_NSE_HEADERS,
                timeout=12,
            )
            self._Loop = current_loop
            self._CookieRefreshTime = None
        return self._Session

    async def close(self) -> None:
        if self._Session:
            try:
                await self._Session.close()
            except Exception:
                pass
            self._Session = None
            self._CookieRefreshTime = None

    async def _soft_initialise(self, force: bool = False) -> None:
        """Warm up cookies at NSE homepage if not done recently."""
        now = datetime.now(timezone.utc)
        if not force and self._CookieRefreshTime and (now - self._CookieRefreshTime).total_seconds() < 300:
            return

        async with self._Lock:
            if not force and self._CookieRefreshTime and (now - self._CookieRefreshTime).total_seconds() < 300:
                return
            session = await self._ensure_session()
            try:
                resp = await session.get(_NSE_BASE_URL, headers=_NSE_HEADERS, timeout=10)
                if resp.status_code == 200:
                    self._CookieRefreshTime = now
                    logger.debug("NSE session warmed up successfully.")
                else:
                    logger.warning("NSE warmup returned status %d", resp.status_code)
            except Exception as exc:
                logger.warning("NSE session warmup error: %s", exc)

    # ── Market Price ─────────────────────────────────────────────

    async def fetch_price(self, symbol: str) -> Optional[dict]:
        """Fetches latest OHLCV snapshot. Uses NSE allIndices for indices, yfinance for stocks."""
        clean_name = symbol.upper().replace(".NS", "").replace(".BO", "")
        if clean_name in INDEX_SYMBOLS or clean_name in _NSE_INDEX_NAME_MAP:
            try:
                index_data = await self._fetch_nse_index_price(clean_name)
                if index_data:
                    return index_data
            except Exception as exc:
                logger.debug("[%s] NSE live index fetch error: %s, falling back to yfinance", symbol, exc)

        return await self._fetch_price_yfinance(symbol)

    async def _fetch_nse_index_price(self, clean_name: str) -> Optional[dict]:
        session = await self._ensure_session()
        await self._soft_initialise()

        target_nse_name = _NSE_INDEX_NAME_MAP.get(clean_name, clean_name)
        resp = await session.get(_NSE_ALL_INDICES_URL, headers=_NSE_API_HEADERS, timeout=8)
        if resp.status_code != 200:
            return None

        data = resp.json()
        indices = data.get("data", [])
        for item in indices:
            if item.get("indexSymbol") == target_nse_name:
                last_p = float(item.get("last", 0.0) or 0.0)
                open_p = float(item.get("open", last_p) or last_p)
                high_p = float(item.get("high", last_p) or last_p)
                low_p = float(item.get("low", last_p) or last_p)
                prev_p = float(item.get("previousClose", last_p) or last_p)
                chg_pct = float(item.get("percentChange", 0.0) or 0.0)

                dy_val = 0.0
                try:
                    dy_val = float(item.get("dy") or 0.0) / 100.0
                except (ValueError, TypeError):
                    dy_val = 0.0

                return {
                    "symbol": clean_name,
                    "last_price": round(last_p, 2),
                    "open": round(open_p, 2),
                    "high": round(high_p, 2),
                    "low": round(low_p, 2),
                    "volume": 0,
                    "previous_close": round(prev_p, 2),
                    "change_percent": round(chg_pct, 2),
                    "currency": "INR",
                    "dividend_yield": round(dy_val, 6),
                    "market_status": _get_market_status().value,
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                }
        return None

    async def _fetch_price_yfinance(self, symbol: str) -> Optional[dict]:
        yf_symbol = _to_yfinance_symbol(symbol)
        market_status = _get_market_status()
        try:
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(None, self._fetch_price_sync, yf_symbol)
            if data:
                data["symbol"] = symbol.upper()
                data["market_status"] = market_status.value
            return data
        except Exception as exc:
            logger.error("[%s] yfinance fetch error: %s", symbol, exc)
            return None

    @staticmethod
    def _fetch_price_sync(yf_symbol: str) -> Optional[dict]:
        try:
            ticker = yf.Ticker(yf_symbol)
            hist = ticker.history(period="5d")
            if hist.empty:
                return None

            hist.columns = [c.lower() for c in hist.columns]
            latest = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) > 1 else latest

            last_price = float(latest["close"])
            prev_close = float(prev["close"])
            change_pct = round(((last_price - prev_close) / prev_close) * 100, 2) if prev_close else 0.0

            cached = _INFO_CACHE.get(yf_symbol)
            if cached and time.monotonic() - cached[0] < _INFO_CACHE_TTL_SECONDS:
                div_yield, currency = cached[1], cached[2]
            else:
                info = ticker.info or {}
                div_yield = NseApiAdapter._dividend_yield_decimal(info, last_price)
                currency = info.get("currency", "INR")
                _INFO_CACHE[yf_symbol] = (time.monotonic(), div_yield, currency)

            return {
                "last_price": round(last_price, 2),
                "open": round(float(latest["open"]), 2),
                "high": round(float(latest["high"]), 2),
                "low": round(float(latest["low"]), 2),
                "volume": int(latest.get("volume", 0)),
                "previous_close": round(prev_close, 2),
                "change_percent": change_pct,
                "currency": currency,
                "dividend_yield": div_yield,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            logger.error("[%s] _fetch_price_sync error: %s", yf_symbol, exc)
            return None

    @staticmethod
    def _dividend_yield_decimal(info: dict, price: float) -> float:
        def positive(key):
            try:
                value = float(info.get(key) or 0.0)
            except (TypeError, ValueError):
                return 0.0
            return value if value > 0 and not math.isnan(value) else 0.0

        rate = positive("dividendRate")
        if rate and price > 0:
            q = rate / price
        elif positive("dividendYield"):
            q = positive("dividendYield") / 100.0
        else:
            q = positive("trailingAnnualDividendYield")
        return round(min(q, 0.25), 6)

    # ── Option Chain ─────────────────────────────────────────────

    async def fetch_expiry_dates(self, symbol: str) -> List[str]:
        """Fetches available option expiry dates for symbol from NSE, formatted as YYYY-MM-DD."""
        clean_name = symbol.upper().replace(".NS", "").replace(".BO", "")
        session = await self._ensure_session()
        await self._soft_initialise()

        try:
            info_url = _NSE_CONTRACT_INFO_URL.format(symbol=clean_name)
            resp = await session.get(info_url, headers=_NSE_API_HEADERS, timeout=8)
            if resp.status_code == 200:
                info_data = resp.json()
                raw_expiries = info_data.get("expiryDates") or info_data.get("metadata", {}).get("expiryDates", [])
                formatted = []
                for exp in raw_expiries:
                    p = self._parse_nse_date(exp)
                    if p and p not in formatted:
                        formatted.append(p)
                if formatted:
                    return formatted
        except Exception as exc:
            logger.warning("[%s] NSE contract-info expiry fetch failed: %s", symbol, exc)

        # Fallback to yfinance if NSE fails
        try:
            yf_chain = await self._fetch_yfinance_options_fallback(symbol)
            if yf_chain and "expiry_dates" in yf_chain:
                return yf_chain["expiry_dates"]
        except Exception as exc:
            logger.warning("[%s] yfinance expiry fetch failed: %s", symbol, exc)

        return []

    async def fetch_option_chain(self, symbol: str) -> List[RawTickDTO]:
        """Fetches full option chain and returns list of RawTickDTOs using real market data."""
        data = await self._fetch_option_chain_raw(symbol)
        if not data:
            logger.warning("[%s] Options data is unavailable across all market sources", symbol)
            return []

        dtos = []
        chains = data.get("chains", {})
        spot_price = float(data.get("spot_price", 0.0) or 0.0)
        for expiry, ticks in chains.items():
            for t in ticks:
                dtos.append(RawTickDTO(
                    symbol=symbol.upper(),
                    expiry=expiry,
                    strike=float(t["strike"]),
                    option_type=t["type"],
                    oi=int(t["oi"]),
                    volume=int(t["volume"]),
                    ltp=float(t["last_price"]),
                    iv=float(t.get("iv", 0.0) or 0.0),
                    bid=float(t.get("bid", 0.0) or 0.0),
                    bid_qty=int(t.get("bid_qty", 0) or 0),
                    ask=float(t.get("ask", 0.0) or 0.0),
                    ask_qty=int(t.get("ask_qty", 0) or 0),
                    underlying_price=spot_price,
                    timestamp=datetime.now(timezone.utc)
                ))
        return dtos

    async def _fetch_option_chain_raw(self, symbol: str) -> Optional[dict]:
        # Precedence 1: NSE Webscraper API via curl_cffi Chrome impersonation
        logger.info("[%s] Attempting option chain retrieval via NSE Webscraper", symbol)
        nse_data = await self._fetch_nse_webscraper_options(symbol)
        if nse_data and nse_data.get("chains"):
            logger.info("[%s] Option chain retrieved via NSE Webscraper with real bid/ask quotes", symbol)
            return nse_data

        # Precedence 2: Yahoo Finance Fallback
        logger.info("[%s] Fallback: Attempting option chain retrieval via Yahoo Finance", symbol)
        return await self._fetch_yfinance_options_fallback(symbol)

    async def _fetch_nse_webscraper_options(self, symbol: str, retry_count: int = 0) -> Optional[dict]:
        clean_name = symbol.upper().replace(".NS", "").replace(".BO", "")
        clean_sym = SymbolValidator.get_clean_symbol(symbol.upper())
        is_nse = clean_sym in INDEX_SYMBOLS or clean_sym.endswith(".NS") or clean_sym.endswith(".BO")
        if not is_nse:
            return None

        m_type = "Indices" if clean_name in INDEX_SYMBOLS else "Equity"
        session = await self._ensure_session()
        await self._soft_initialise()

        try:
            # 1. Fetch Contract Info (Expiries)
            info_url = _NSE_CONTRACT_INFO_URL.format(symbol=clean_name)
            resp = await session.get(info_url, headers=_NSE_API_HEADERS, timeout=10)
            if resp.status_code in (401, 403) and retry_count < 2:
                await self._soft_initialise(force=True)
                return await self._fetch_nse_webscraper_options(symbol, retry_count + 1)

            if resp.status_code != 200:
                logger.warning("[%s] NSE contract info returned status %d", clean_name, resp.status_code)
                return None

            info_data = resp.json()
            raw_expiries = info_data.get("expiryDates") or info_data.get("metadata", {}).get("expiryDates", [])
            if not raw_expiries:
                return None

            # 2. Fetch v3 chain for the first 2 expiries
            combined_data = {"records": {"underlyingValue": 0, "expiryDates": raw_expiries, "data": []}}
            for exp in raw_expiries[:2]:
                v3_url = _NSE_OPTION_CHAIN_V3_URL.format(type=m_type, symbol=clean_name, expiry=exp)
                v3_resp = await session.get(v3_url, headers=_NSE_API_HEADERS, timeout=10)
                if v3_resp.status_code == 200:
                    raw_v3 = v3_resp.json()
                    v3_ticks = raw_v3.get("data", []) or raw_v3.get("records", {}).get("data", [])
                    if v3_ticks:
                        combined_data["records"]["data"].extend(v3_ticks)
                        spot = (
                            raw_v3.get("metadata", {}).get("underlyingValue", 0)
                            or raw_v3.get("records", {}).get("underlyingValue", 0)
                        )
                        if spot:
                            combined_data["records"]["underlyingValue"] = spot

            if not combined_data["records"]["data"]:
                return None

            return self._parse_option_chain(symbol, combined_data)

        except Exception as exc:
            logger.warning("[%s] NSE Webscraper fetch error: %s", symbol, exc)
            return None

    @classmethod
    def _parse_nse_date(cls, date_str: str) -> Optional[str]:
        """Convert NSE date format ('23-Nov-2026', '23-11-2026') to YYYY-MM-DD."""
        if not date_str:
            return None
        cleaned = str(date_str).strip()
        for fmt in ("%d-%b-%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                continue
        return None

    @classmethod
    def _parse_option_chain(cls, symbol: str, data: dict) -> Optional[dict]:
        records = data.get("records", {})
        underlying = records.get("underlyingValue", 0)
        expiry_dates_raw = records.get("expiryDates", [])
        all_data = records.get("data", [])

        chains: dict[str, list[dict]] = {}
        for row in all_data:
            strike = row.get("strikePrice")
            raw_exp = row.get("expiryDate") or row.get("expiryDates")
            if not raw_exp and row.get("CE"):
                raw_exp = row["CE"].get("expiryDate")
            if not raw_exp and row.get("PE"):
                raw_exp = row["PE"].get("expiryDate")

            expiry = cls._parse_nse_date(raw_exp)
            if not strike or not expiry:
                continue

            if expiry not in chains:
                chains[expiry] = []

            for opt_key in ["CE", "PE"]:
                opt = row.get(opt_key)
                if not opt:
                    continue

                lp = float(opt.get("lastPrice", 0) or 0)
                oi = int(opt.get("openInterest", 0) or 0)
                if lp > 0 or oi > 0:
                    bid_p = float(opt.get("buyPrice1", 0.0) or opt.get("bid", 0.0) or 0.0)
                    bid_q = int(opt.get("buyQuantity1", 0) or opt.get("bid_qty", 0) or 0)
                    ask_p = float(opt.get("sellPrice1", 0.0) or opt.get("ask", 0.0) or 0.0)
                    ask_q = int(opt.get("sellQuantity1", 0) or opt.get("ask_qty", 0) or 0)
                    iv_val = float(opt.get("impliedVolatility", 0.0) or 0.0) / 100.0

                    chains[expiry].append({
                        "strike": float(strike),
                        "type": opt_key,
                        "last_price": lp,
                        "oi": oi,
                        "volume": int(opt.get("totalTradedVolume", 0) or 0),
                        "iv": iv_val,
                        "bid": bid_p,
                        "bid_qty": bid_q,
                        "ask": ask_p,
                        "ask_qty": ask_q,
                        "expiry": expiry,
                    })

        parsed_expiries = []
        for e in expiry_dates_raw:
            pe = cls._parse_nse_date(e)
            if pe and pe not in parsed_expiries:
                parsed_expiries.append(pe)

        return {
            "symbol": symbol.upper(),
            "spot_price": float(underlying),
            "expiry_dates": parsed_expiries if parsed_expiries else sorted(chains.keys()),
            "chains": chains,
        }

    async def _fetch_yfinance_options_fallback(self, symbol: str) -> Optional[dict]:
        return await asyncio.to_thread(self._fetch_yfinance_options_sync, symbol)

    @staticmethod
    def _fetch_yfinance_options_sync(symbol: str) -> Optional[dict]:
        def num(value, cast=float):
            try:
                value = float(value)
            except (TypeError, ValueError):
                return cast(0)
            return cast(0) if math.isnan(value) else cast(value)

        def rows_to_ticks(frame, option_type: str, expiry: str) -> list[dict]:
            return [{
                "strike": num(r.get("strike")),
                "type": option_type,
                "last_price": num(r.get("lastPrice")),
                "oi": num(r.get("openInterest"), int),
                "volume": num(r.get("volume"), int),
                "iv": num(r.get("impliedVolatility")),
                "bid": num(r.get("bid")),
                "ask": num(r.get("ask")),
                "expiry": expiry,
            } for _, r in frame.iterrows()]

        try:
            ticker = yf.Ticker(_to_yfinance_symbol(symbol))
            expiries = ticker.options
            if not expiries:
                return None

            spot = ticker.fast_info.get("last_price", 0) if ticker.fast_info else 0
            chains = {}
            for exp in expiries[:2]:
                opt = ticker.option_chain(exp)
                chains[exp] = rows_to_ticks(opt.calls, "CE", exp) + rows_to_ticks(opt.puts, "PE", exp)

            return {
                "symbol": symbol.upper(),
                "spot_price": num(spot),
                "expiry_dates": list(expiries),
                "chains": chains,
            }
        except Exception as exc:
            logger.warning("[%s] yfinance option chain fallback failed: %s", symbol, exc)
            return None
