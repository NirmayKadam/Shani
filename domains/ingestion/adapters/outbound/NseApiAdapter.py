from domains.ingestion.ports.outbound.IMarketDataSource import IMarketDataSource
from domains.ingestion.dto.RawTickDTO import RawTickDTO
from typing import List

# app/domain/ingestion/market_data_fetcher.py — Market price + NSE option chain fetcher
#
# Two independent fetchers:
#   1. MarketPriceFetcher — uses yfinance for OHLCV snapshots (works when market is closed)
#   2. OptionChainFetcher — fetches full option chain from NSE India API (all expiries)

import os
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiohttp
import yfinance as yf

from app.shared.constants import MarketStatus, INDEX_SYMBOLS

Logger = logging.getLogger(__name__)

# ── NSE India API Configuration ────────────────────────────────

_NSE_BASE_URL = "https://www.nseindia.com"
_NSE_OPTION_CHAIN_INDEX_URL = "https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
_NSE_OPTION_CHAIN_EQUITY_URL = "https://www.nseindia.com/api/option-chain-equities?symbol={symbol}"
_NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/option-chain",
    "Connection": "keep-alive",
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
    if not upper.endswith(".NS"):
        return f"{upper}.NS"
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
            Logger.error("[%s] yfinance fetch error: %s", symbol, exc)
            return None

    @staticmethod
    def _fetch_sync(yf_symbol: str) -> Optional[dict]:
        """Synchronous yfinance call — runs in thread pool."""
        try:
            ticker = yf.Ticker(yf_symbol)

            # Get last 5 days to ensure we have data even after weekends
            hist = ticker.history(period="5d")
            if hist.empty:
                Logger.warning("[%s] yfinance returned empty history", yf_symbol)
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
                "last_updated": str(hist.index[-1].date()),
            }
        except Exception as exc:
            Logger.error("[%s] _fetch_sync error: %s", yf_symbol, exc)
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

    async def _refresh_cookies(self) -> None:
        """Visit NSE homepage to grab fresh session cookies (expire ~5 min)."""
        now = datetime.now(timezone.utc)
        if (
            self._CookieRefreshTime is not None
            and (now - self._CookieRefreshTime).total_seconds() < 240
        ):
            return

        Logger.info("Refreshing NSE session cookies...")
        try:
            async with self._Session.get(_NSE_BASE_URL) as resp:
                self._CookieRefreshTime = now
                cookie_count = len(self._Session.cookie_jar)
                Logger.info("NSE cookies refreshed (%d cookies)", cookie_count)
        except Exception as exc:
            Logger.error("Failed to refresh NSE cookies: %s", exc)
            raise

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

        await self._refresh_cookies()

        # Choose correct endpoint
        if symbol.upper() in INDEX_SYMBOLS:
            url = _NSE_OPTION_CHAIN_INDEX_URL.format(symbol=symbol.upper())
        else:
            url = _NSE_OPTION_CHAIN_EQUITY_URL.format(symbol=symbol.upper())

        try:
            async with self._Session.get(url) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    Logger.warning(
                        "[%s] NSE API returned %d: %s",
                        symbol, resp.status, body[:300],
                    )
                    return None

                raw_data = await resp.json()

        except aiohttp.ContentTypeError:
            Logger.warning("[%s] NSE returned non-JSON response", symbol)
            return None
        except Exception as exc:
            Logger.warning("[%s] NSE fetch error: %s", symbol, exc)
            return None

        return self._parse_option_chain(symbol, raw_data)

    @staticmethod
    def _parse_option_chain(symbol: str, data: dict) -> Optional[dict]:
        """Parse NSE option chain JSON into structured format with all expiries."""
        records = data.get("records", {})
        underlying = records.get("underlyingValue", 0)
        expiry_dates_raw = records.get("expiryDates", [])
        all_data = data.get("filtered", {}).get("data", []) or records.get("data", [])

        if not all_data:
            Logger.warning("[%s] NSE returned empty option chain", symbol)
            return None

        # Convert date format and build chains per expiry
        chains: dict[str, list[dict]] = {}
        expiry_dates_iso: list[str] = []

        for raw_date in expiry_dates_raw:
            try:
                dt = datetime.strptime(raw_date, "%d-%b-%Y")
                iso = dt.strftime("%Y-%m-%d")
                expiry_dates_iso.append(iso)
            except (ValueError, TypeError):
                continue

        total_ce = 0
        total_pe = 0

        for row in all_data:
            strike = row.get("strikePrice", 0)
            row_expiry_raw = row.get("expiryDate", "")

            # Convert expiry
            try:
                expiry_iso = datetime.strptime(row_expiry_raw, "%d-%b-%Y").strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                continue

            if expiry_iso not in chains:
                chains[expiry_iso] = []

            # Parse CE
            ce = row.get("CE")
            if ce and ce.get("lastPrice", 0) > 0:
                chains[expiry_iso].append({
                    "strike": float(strike),
                    "type": "CE",
                    "last_price": float(ce.get("lastPrice", 0)),
                    "oi": int(ce.get("openInterest", 0)),
                    "volume": int(ce.get("totalTradedVolume", 0)),
                    "expiry": expiry_iso,
                })
                total_ce += 1

            # Parse PE
            pe = row.get("PE")
            if pe and pe.get("lastPrice", 0) > 0:
                chains[expiry_iso].append({
                    "strike": float(strike),
                    "type": "PE",
                    "last_price": float(pe.get("lastPrice", 0)),
                    "oi": int(pe.get("openInterest", 0)),
                    "volume": int(pe.get("totalTradedVolume", 0)),
                    "expiry": expiry_iso,
                })
                total_pe += 1

        unique_strikes = len(set(
            t["strike"] for chain in chains.values() for t in chain
        ))

        Logger.info(
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


class NseApiAdapter(IMarketDataSource):
    def __init__(self):
        self._fetcher = OptionChainFetcher()
        
    async def fetch_option_chain(self, symbol: str) -> List[RawTickDTO]:
        data = await self._fetcher.fetch(symbol)
        # map to DTO
        dtos = []
        if not data: return dtos
        
        chains = data.get('chains', {})
        for expiry, ticks in chains.items():
            for t in ticks:
                from datetime import datetime
                dtos.append(RawTickDTO(
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
