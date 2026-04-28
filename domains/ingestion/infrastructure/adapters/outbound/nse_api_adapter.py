"""
File Overview: Outbound adapter for NSE India and yfinance. Handles market price and option chain retrieval.

All Functions/Classes:
- MarketPriceFetcher: Price snapshot engine via yfinance. Take symbol and send OHLCV data.
- OptionChainFetcher: Derivatives data engine via NSE V3 API. Take symbol and send structured chain with spot price.
- nse_api_adapter: Port implementation for market data. Take symbol and send raw_tick_dto list via option chain fetcher.

Endpoints/APIs: NSE India API, yfinance API

Database Tables: None
"""

import os
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from domains.ingestion.application.ports.interface.outbound.i_market_data_source import i_market_data_source
from domains.ingestion.application.dto.raw_tick_dto import raw_tick_dto

import aiohttp
import yfinance as yf

from shared.constants import MarketStatus, INDEX_SYMBOLS

logger = logging.getLogger(__name__)

# ── NSE India API Configuration ────────────────────────────────

_NSE_BASE_URL = "https://www.nseindia.com"
_NSE_CONTRACT_INFO_URL = "https://www.nseindia.com/api/option-chain-contract-info?symbol={symbol}"
_NSE_OPTION_CHAIN_V3_URL = "https://www.nseindia.com/api/option-chain-v3?type={type}&symbol={symbol}&expiry={expiry}"

_NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

_NSE_API_HEADERS = {
    "host": "www.nseindia.com",
    "User-Agent": _NSE_HEADERS["User-Agent"],
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://www.nseindia.com/option-chain",
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
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
    
    # If it's already an index or has a suffix/special char, leave it
    if "^" in upper or "." in upper:
        return upper
        
    # Heuristic: If it's alphanumeric and we don't know it, 
    # we'll try to see if it's valid as is first (in the fetcher)
    return upper


def _get_market_status() -> MarketStatus:
    """
    Determine if Indian market (NSE) is currently open.
    Market hours: 9:15 AM to 3:30 PM IST, Monday to Friday.
    """
    import pytz
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)

    # Weekend check
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
# Market Price Fetcher (yfinance)
# ═══════════════════════════════════════════════════════════════

class MarketPriceFetcher:
    """
    Fetches current/last-close OHLCV data via yfinance.
    Always returns data even when market is closed — uses last trading day.

    Usage:
        fetcher = MarketPriceFetcher()
        data = await fetcher.fetch("NIFTY")
    """

    async def fetch(self, symbol: str) -> Optional[dict]:
        """
        Fetch the latest OHLCV snapshot for a symbol.

        Returns:
            {
                "symbol": "NIFTY",
                "last_price": 22500.50,
                "open": 22400.00,
                "high": 22550.00,
                "low": 22380.00,
                "volume": 12345678,
                "previous_close": 22450.00,
                "change_percent": 0.22,
                "market_status": "OPEN",
                "last_updated": "2026-04-12"
            }

        Returns None only on catastrophic error. Always returns last-close
        data when market is closed.
        """
        yf_symbol = _to_yfinance_symbol(symbol)
        market_status = _get_market_status()

        try:
            # Run yfinance in a thread to avoid blocking the event loop
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(
                None, self._fetch_sync, yf_symbol
            )

            if data is None:
                return None

            data["symbol"] = symbol.upper()
            data["market_status"] = market_status.value
            return data

        except Exception as exc:
            logger.error("[%s] yfinance fetch error: %s", symbol, exc)
            return None

    @staticmethod
    def _fetch_sync(yf_symbol: str) -> Optional[dict]:
        """Synchronous yfinance call — runs in thread pool."""
        try:
            ticker = yf.Ticker(yf_symbol)

            # Get last 5 days to ensure we have data even after weekends
            hist = ticker.history(period="5d")
            if hist.empty:
                logger.warning("[%s] yfinance returned empty history", yf_symbol)
                return None

            hist.columns = [c.lower() for c in hist.columns]
            latest = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) > 1 else latest

            last_price = float(latest["close"])
            prev_close = float(prev["close"])
            change_pct = round(((last_price - prev_close) / prev_close) * 100, 2) if prev_close else 0.0

            return {
                "last_price": round(last_price, 2),
                "open": round(float(latest["open"]), 2),
                "high": round(float(latest["high"]), 2),
                "low": round(float(latest["low"]), 2),
                "volume": int(latest.get("volume", 0)),
                "previous_close": round(prev_close, 2),
                "change_percent": change_pct,
                "currency": ticker.info.get("currency", "USD" if ".NS" not in yf_symbol and "^" not in yf_symbol else "INR"),
                "last_updated": str(hist.index[-1].date()),
            }
        except Exception as exc:
            logger.error("[%s] _fetch_sync error: %s", yf_symbol, exc)
            return None


# ═══════════════════════════════════════════════════════════════
# Option Chain Fetcher (NSE India API)
# ═══════════════════════════════════════════════════════════════

class OptionChainFetcher:
    """
    Fetches full option chain from NSE India API — ALL expiries.

    Usage:
        fetcher = OptionChainFetcher()
        await fetcher.initialise()
        data = await fetcher.fetch("NIFTY")
        await fetcher.close()
    """

    def __init__(self) -> None:
        self._Session: Optional[aiohttp.ClientSession] = None
        self._CookieRefreshTime: Optional[datetime] = None

    async def initialise(self) -> None:
        self._Session = aiohttp.ClientSession(
            headers=_NSE_HEADERS,
            timeout=aiohttp.ClientTimeout(total=30),
        )

    async def close(self) -> None:
        if self._Session and not self._Session.closed:
            await self._Session.close()

    async def _soft_initialise(self, symbol: str, force: bool = False) -> None:
        """Establish session by visiting the specific symbol page and softening with API calls."""
        now = datetime.now(timezone.utc)
        if (
            not force
            and self._CookieRefreshTime is not None
            and (now - self._CookieRefreshTime).total_seconds() < 600
        ):
            return

        logger.info("[%s] Initialising NSE session...", symbol)
        try:
            # 1. Base URL
            async with self._Session.get(_NSE_BASE_URL, headers=_NSE_HEADERS) as resp:
                await asyncio.sleep(1.0)
                
            # 2. Main Option Chain Page with specific symbol
            url = f"https://www.nseindia.com/option-chain?symbol={symbol}"
            headers = _NSE_HEADERS.copy()
            headers["Referer"] = _NSE_BASE_URL
            async with self._Session.get(url, headers=headers) as resp:
                self._CookieRefreshTime = now
                await asyncio.sleep(1.0)
                
            # 3. Soften with master-quote
            async with self._Session.get("https://www.nseindia.com/api/master-quote", headers=_NSE_API_HEADERS) as resp:
                await asyncio.sleep(0.5)

            # 4. Legacy endpoint nudge (sets some backend session state even if 401)
            legacy_url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}" if symbol in INDEX_SYMBOLS else f"https://www.nseindia.com/api/option-chain-equities?symbol={symbol}"
            async with self._Session.get(legacy_url, headers=_NSE_API_HEADERS) as resp:
                await asyncio.sleep(0.5)
                
            logger.info("[%s] Session established (%d cookies)", symbol, len(self._Session.cookie_jar))
                
        except Exception as exc:
            logger.error("[%s] Session init failed: %s", symbol, exc)

    async def fetch(self, symbol: str) -> Optional[dict]:
        """
        Fetch the full option chain for a symbol from NSE.

        Returns:
            {
                "symbol": "NIFTY",
                "spot_price": 22500.0,
                "expiry_dates": ["2026-04-17", "2026-04-24", "2026-05-29"],
                "chains": {
                    "2026-04-17": [
                        {"strike": 22400, "type": "CE", "last_price": 150.5,
                         "oi": 50000, "volume": 12345, "expiry": "2026-04-17"},
                        ...
                    ],
                    "2026-04-24": [...],
                },
                "summary": {
                    "total_ce": 42,
                    "total_pe": 42,
                    "total_strikes": 42
                }
            }

        Returns None if NSE is unreachable (market closed, rate limited).
        """
        if self._Session is None or self._Session.closed:
            await self.initialise()

        await self._soft_initialise(symbol)

        # Detect if it's an NSE symbol. NSE symbols are typically letters-only
        # or known indices. International ones often have suffixes or different formats.
        from shared.utils.symbol_validator import SymbolValidator
        clean_sym = SymbolValidator.get_clean_symbol(symbol.upper())
        is_nse = clean_sym in INDEX_SYMBOLS or clean_sym.endswith(".NS") or clean_sym.endswith(".BO")

        if not is_nse:
             logger.info("[%s] Non-NSE symbol detected, using yfinance for options", symbol)
             return await self._fetch_yfinance_fallback(symbol)

        # Choose correct endpoint and type
        symbol_upper = symbol.upper()
        clean_name = symbol_upper.replace(".NS", "")
        m_type = "Indices" if symbol_upper in INDEX_SYMBOLS else "Equity"

        try:
            # 1. Get Expiries from contract-info
            info_url = _NSE_CONTRACT_INFO_URL.format(symbol=clean_name)
            async with self._Session.get(info_url, headers=_NSE_API_HEADERS) as resp:
                if resp.status == 401:
                    await self._soft_initialise(symbol, force=True)
                    return await self.fetch(symbol) # Recursive retry once
                
                if resp.status != 200:
                    return await self._fetch_yfinance_fallback(symbol)
                
                info_data = await resp.json()
                expiries = info_data.get("expiryDates") or info_data.get("metadata", {}).get("expiryDates", [])
                
                if not expiries:
                    logger.warning("[%s] No expiries found in NSE contract info", symbol)
                    return await self._fetch_yfinance_fallback(symbol)

            # 2. Fetch v3 chain for the first 2 expiries
            combined_data = {"records": {"underlyingValue": 0, "expiryDates": expiries, "data": []}}
            
            for exp in expiries[:2]:
                v3_url = _NSE_OPTION_CHAIN_V3_URL.format(type=m_type, symbol=clean_name, expiry=exp)
                async with self._Session.get(v3_url, headers=_NSE_API_HEADERS) as resp:
                    if resp.status == 401:
                        logger.info("[%s] Session expired on v3 fetch, refreshing...", symbol)
                        await self._soft_initialise(symbol, force=True)
                        # No recursion here to avoid infinite loop, loop will continue for next exp
                        continue

                    if resp.status != 200:
                        logger.warning("[%s] NSE v3 fetch failed for %s: %d", symbol, exp, resp.status)
                        continue
                        
                    raw_v3 = await resp.json()
                    # v3 can return data at root or under records
                    v3_ticks = raw_v3.get("data", []) or raw_v3.get("records", {}).get("data", [])
                    
                    if v3_ticks:
                        combined_data["records"]["data"].extend(v3_ticks)
                        spot = raw_v3.get("metadata", {}).get("underlyingValue", 0) or raw_v3.get("records", {}).get("underlyingValue", 0)
                        if spot: combined_data["records"]["underlyingValue"] = spot

            if not combined_data["records"]["data"]:
                logger.warning("[%s] All NSE v3 fetch attempts failed or returned empty", symbol)
                return await self._fetch_yfinance_fallback(symbol)

            return self._parse_option_chain(symbol, combined_data)

        except Exception as exc:
            logger.warning("[%s] NSE fetch error: %s - trying yfinance fallback", symbol, exc)
            return await self._fetch_yfinance_fallback(symbol)

    async def _fetch_yfinance_fallback(self, symbol: str) -> Optional[dict]:
        """Fetch option chain using yfinance for non-NSE symbols or as backup."""
        logger.info("[%s] Fetching option chain via yfinance fallback", symbol)
        try:
            from shared.utils.symbol_validator import SymbolValidator
            clean_sym = SymbolValidator.get_clean_symbol(symbol)
            ticker = yf.Ticker(clean_sym)
            
            expiries = ticker.options
            if not expiries:
                logger.info("[%s] No options available via yfinance", symbol)
                return None
                
            # Just fetch the first 2 expiries to keep it light
            chains = {}
            total_ce = 0
            total_pe = 0
            
            import pandas as pd
            import numpy as np

            # Map NIFTY names if needed for spot
            fast = ticker.fast_info
            spot = fast.get('last_price', 0) if fast else 0
            
            for exp in expiries[:3]:
                opt = ticker.option_chain(exp)
                exp_ticks = []
                
                def _to_int(val):
                    try:
                        if pd.isna(val) or val is None: return 0
                        return int(val)
                    except: return 0

                def _to_float(val):
                    try:
                        if pd.isna(val) or val is None: return 0.0
                        return float(val)
                    except: return 0.0

                for _, row in opt.calls.iterrows():
                    exp_ticks.append({
                        "strike": _to_float(row['strike']),
                        "type": "CE",
                        "last_price": _to_float(row['lastPrice']),
                        "oi": _to_int(row.get('openInterest')),
                        "volume":_to_int(row.get('volume')),
                        "expiry": exp
                    })
                    total_ce += 1
                for _, row in opt.puts.iterrows():
                    exp_ticks.append({
                        "strike": _to_float(row['strike']),
                        "type": "PE",
                        "last_price": _to_float(row['lastPrice']),
                        "oi": _to_int(row.get('openInterest')),
                        "volume": _to_int(row.get('volume')),
                        "expiry": exp
                    })
                    total_pe += 1
                chains[exp] = exp_ticks
                
            return {
                "symbol": symbol.upper(),
                "spot_price": float(spot),
                "expiry_dates": list(expiries),
                "chains": chains,
                "summary": {
                    "total_ce": total_ce,
                    "total_pe": total_pe,
                    "total_strikes": len(chains.get(expiries[0], [])) // 2 if expiries else 0
                }
            }
        except Exception as exc:
            logger.error("[%s] yfinance options fallback failed: %s", symbol, exc)
            return None

    @staticmethod
    def _parse_nse_date(date_str: str) -> Optional[str]:
        """Helper to parse 'DD-MMM-YYYY' or 'DD-MM-YYYY' safely."""
        months = {
            "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
            "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
            "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"
        }
        try:
            parts = date_str.split("-")
            if len(parts) != 3: return None
            d, m, y = parts
            
            if m.isdigit():
                m_num = m.zfill(2)
            else:
                m_num = months.get(m.capitalize())
                
            if not m_num: return None
            return f"{y}-{m_num}-{d.zfill(2)}"
        except:
            return None

    @staticmethod
    def _parse_option_chain(symbol: str, data: dict) -> Optional[dict]:
        """Parse NSE option chain JSON into structured format with all expiries."""
        records = data.get("records", {})
        underlying = records.get("underlyingValue", 0)
        expiry_dates_raw = records.get("expiryDates", [])
        all_data = data.get("filtered", {}).get("data", []) or records.get("data", [])
        logger.info("[%s] Processing %d ticks", symbol, len(all_data))

        if not all_data:
            logger.warning("[%s] NSE returned empty option chain", symbol)
            return None

        # Convert date format and build chains per expiry
        chains: dict[str, list[dict]] = {}
        expiry_dates_iso: list[str] = []

        for raw_date in expiry_dates_raw:
            iso = OptionChainFetcher._parse_nse_date(raw_date)
            if iso:
                expiry_dates_iso.append(iso)

        total_ce = 0
        total_pe = 0

        for row in all_data:
            # v3 might have strikePrice and expiryDate at root or nested
            strike = row.get("strikePrice", 0)
            row_expiry_raw = row.get("expiryDate", "")
            
            if not strike or not row_expiry_raw:
                # Try fallback to CE/PE sub-objects
                sub = row.get("CE") or row.get("PE")
                if sub:
                    strike = strike or sub.get("strikePrice", 0)
                    row_expiry_raw = row_expiry_raw or sub.get("expiryDate", "")

            if not strike or not row_expiry_raw:
                continue

            # Convert expiry
            expiry_iso = OptionChainFetcher._parse_nse_date(row_expiry_raw)
            if not expiry_iso:
                continue

            if expiry_iso not in chains:
                chains[expiry_iso] = []

            # v3 usually has nested CE/PE but also might have flattened 'type'
            found_any = False
            for opt_key in ["CE", "PE"]:
                opt_data = row.get(opt_key)
                if opt_data:
                    lp = opt_data.get("last_price", opt_data.get("lastPrice", 0))
                    if lp > 0:
                        chains[expiry_iso].append({
                            "strike": float(strike),
                            "type": opt_key,
                            "last_price": float(lp),
                            "oi": int(opt_data.get("openInterest", opt_data.get("OI", 0))),
                            "volume": int(opt_data.get("totalTradedVolume", opt_data.get("volume", 0))),
                            "expiry": expiry_iso,
                        })
                        if opt_key == "CE": total_ce += 1
                        else: total_pe += 1
                        found_any = True

            # Fallback for flattened structure (some v3 variants)
            if not found_any:
                row_type = row.get("type")
                if row_type:
                    lp = row.get("lastPrice", 0)
                    if lp > 0:
                        chains[expiry_iso].append({
                            "strike": float(strike),
                            "type": row_type,
                            "last_price": float(lp),
                            "oi": int(row.get("openInterest", 0)),
                            "volume": int(row.get("totalTradedVolume", 0)),
                            "expiry": expiry_iso,
                        })
                        if row_type == "CE": total_ce += 1
                        else: total_pe += 1

        unique_strikes = len(set(
            t["strike"] for chain in chains.values() for t in chain
        ))

        logger.info(
            "[%s] Parsed option chain: %d expiries, %d CE + %d PE ticks, spot=%.2f",
            symbol, len(chains), total_ce, total_pe, underlying,
        )

        return {
            "symbol": symbol.upper(),
            "spot_price": float(underlying),
            "expiry_dates": expiry_dates_iso,
            "chains": chains,
            "summary": {
                "total_ce": total_ce,
                "total_pe": total_pe,
                "total_strikes": unique_strikes,
            },
        }

class nse_api_adapter(i_market_data_source):
    def __init__(self):
        self._fetcher = OptionChainFetcher()
        
    async def fetch_option_chain(self, symbol: str) -> List[raw_tick_dto]:
        data = await self._fetcher.fetch(symbol)
        # map to DTO
        dtos = []
        if not data: return dtos
        
        chains = data.get('chains', {})
        for expiry, ticks in chains.items():
            for t in ticks:
                from datetime import datetime
                dtos.append(raw_tick_dto(
                    symbol=symbol,
                    expiry=expiry,
                    strike=t['strike'],
                    option_type=t['type'],
                    oi=t['oi'],
                    volume=t['volume'],
                    ltp=t['last_price'],
                    timestamp=datetime.now()
                ))
        return dtos
