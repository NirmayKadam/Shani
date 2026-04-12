"""
TickIngestor — consumes live market ticks from NSE India API
and persists them into the TickData TimescaleDB hypertable.

Data Sources (in priority order):
    1. NSE India API (default, free, no key needed)
    2. Mock data generator (fallback for testing / when NSE is down)

The NSE API returns the full option chain with:
    - All strikes (CE + PE)
    - Last traded price (premium)
    - Open Interest, change in OI
    - Volume
    - Underlying spot price

Lifecycle:
    Ingestor = TickIngestor()
    await Ingestor.Initialise()
    await Ingestor.IngestOnce()        # one-shot cycle
    await Ingestor.RunForever()        # or continuous loop
    await Ingestor.Shutdown()
"""

import os
import math
import random
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional
from dataclasses import dataclass, field, asdict

import asyncpg
import aiohttp
import redis.asyncio as aioredis

Logger = logging.getLogger(__name__)
Logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))


# ── Domain Model ────────────────────────────────────────────────

@dataclass
class TickRecord:
    """Mirrors the TickData hypertable columns."""
    Timestamp: str
    Symbol: str
    Exchange: str
    InstrumentType: str        # EQ | FUT | CE | PE
    LastPrice: float
    OpenInterest: int = 0
    Volume: int = 0
    ExpiryDate: Optional[str] = None
    StrikePrice: Optional[float] = None

    def ToDict(self) -> dict:
        return asdict(self)


# ── Configuration ───────────────────────────────────────────────

_DATABASE_URL: str = os.getenv(
    "DATABASE_URL", "postgresql://localhost:5432/postgres"
)
_REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
_POLL_INTERVAL: int = int(os.getenv("TICK_POLL_INTERVAL_SECONDS", "30"))

_WATCHLIST: list[str] = [
    s.strip()
    for s in os.getenv("WATCHLIST_SYMBOLS", "NIFTY,RELIANCE,INFY").split(",")
    if s.strip()
]

# NSE India API configuration
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

# Symbols that are indices (use option-chain-indices endpoint)
_INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}


# ── TickIngestor ────────────────────────────────────────────────

class TickIngestor:
    """
    Lifecycle:
        Ingestor = TickIngestor()
        await Ingestor.Initialise()
        await Ingestor.IngestOnce()
        await Ingestor.Shutdown()
    """

    def __init__(self) -> None:
        self._DbPool: Optional[asyncpg.Pool] = None
        self._Redis: Optional[aioredis.Redis] = None
        self._HttpSession: Optional[aiohttp.ClientSession] = None
        self._NseCookies: Optional[dict] = None
        self._CookieRefreshTime: Optional[datetime] = None
        self._ReconnectDelay: float = 1.0

    # ── Lifecycle ───────────────────────────────────────────────

    async def Initialise(self) -> None:
        """Spin up DB pool, Redis connection, and HTTP session."""
        Logger.info("Initialising TickIngestor...")

        self._DbPool = await asyncpg.create_pool(
            dsn=_DATABASE_URL, min_size=2, max_size=5
        )
        Logger.info("Database pool ready  (%s)", _DATABASE_URL.split("@")[-1])

        self._Redis = aioredis.from_url(_REDIS_URL, decode_responses=True)
        await self._Redis.ping()
        Logger.info("Redis connected  (%s)", _REDIS_URL)

        self._HttpSession = aiohttp.ClientSession(
            headers=_NSE_HEADERS,
            timeout=aiohttp.ClientTimeout(total=30),
        )
        Logger.info("HTTP session created for NSE API")

    async def Shutdown(self) -> None:
        """Graceful teardown."""
        if self._HttpSession and not self._HttpSession.closed:
            await self._HttpSession.close()
        if self._Redis:
            await self._Redis.aclose()
        if self._DbPool:
            await self._DbPool.close()
        Logger.info("TickIngestor shut down cleanly")

    def IsReady(self) -> bool:
        return all([self._DbPool, self._Redis, self._HttpSession])

    # ── Public API ──────────────────────────────────────────────

    async def IngestOnce(self) -> list[TickRecord]:
        """
        Execute a single ingestion cycle.
        Fetches option chain data from NSE for each watchlist symbol.
        Falls back to mock data if NSE is unreachable.
        """
        if not self.IsReady():
            raise RuntimeError("TickIngestor not initialised — call Initialise() first")

        AllTicks: list[TickRecord] = []

        for Symbol in _WATCHLIST:
            try:
                Ticks = await self._FetchFromNSE(Symbol)
                if Ticks:
                    AllTicks.extend(Ticks)
                    Logger.info("[%s] Fetched %d ticks from NSE", Symbol, len(Ticks))
                else:
                    Logger.warning(
                        "[%s] NSE returned no ticks.",
                        Symbol,
                    )
            except Exception as Exc:
                Logger.warning(
                    "[%s] NSE fetch failed: %s",
                    Symbol, Exc,
                )

            # Small delay between symbols to avoid rate limiting
            await asyncio.sleep(1.5)

        if not AllTicks:
            Logger.warning("No ticks generated in this cycle")
            return []

        # Persist all ticks to TimescaleDB
        Saved = await self._SaveTickBatch(AllTicks)
        Logger.info("Persisted %d ticks to TickData hypertable", Saved)

        # Dispatch to derivatives queue for MetricsComputer processing
        self._DispatchToDerivativesQueue(AllTicks)

        # Reset reconnect delay on success
        self._ReconnectDelay = 1.0

        return AllTicks

    async def RunForever(self) -> None:
        """Blocking poll loop."""
        Logger.info(
            "Starting continuous tick ingestion  (interval=%ds, symbols=%s)",
            _POLL_INTERVAL, _WATCHLIST,
        )
        while True:
            try:
                await self.IngestOnce()
            except Exception as Exc:
                Logger.error("Tick ingestion cycle error: %s", Exc, exc_info=True)
                await asyncio.sleep(self._ReconnectDelay)
                self._ReconnectDelay = min(self._ReconnectDelay * 2, 60.0)
                continue
            await asyncio.sleep(_POLL_INTERVAL)

    # ── NSE India API ──────────────────────────────────────────

    async def _RefreshNseCookies(self) -> None:
        """
        Visit the NSE homepage to grab fresh session cookies.
        Cookies expire roughly every 5 minutes.
        """
        Now = datetime.now(timezone.utc)
        if (
            self._NseCookies is not None
            and self._CookieRefreshTime is not None
            and (Now - self._CookieRefreshTime).total_seconds() < 240  # refresh every 4 min
        ):
            return  # cookies are still fresh

        Logger.info("Refreshing NSE session cookies...")
        try:
            async with self._HttpSession.get(_NSE_BASE_URL) as Resp:
                # Extract cookies from the response
                self._NseCookies = {
                    cookie.key: cookie.value
                    for cookie in self._HttpSession.cookie_jar
                }
                self._CookieRefreshTime = Now
                Logger.info(
                    "NSE cookies refreshed (%d cookies captured)",
                    len(self._NseCookies),
                )
        except Exception as Exc:
            Logger.error("Failed to refresh NSE cookies: %s", Exc)
            raise

    async def _FetchFromNSE(self, Symbol: str) -> list[TickRecord]:
        """
        Fetch the full option chain for a symbol from NSE India API.
        Returns a list of TickRecord objects.
        """
        # Ensure we have fresh cookies
        await self._RefreshNseCookies()

        # Choose the correct endpoint
        if Symbol.upper() in _INDEX_SYMBOLS:
            Url = _NSE_OPTION_CHAIN_INDEX_URL.format(symbol=Symbol.upper())
        else:
            Url = _NSE_OPTION_CHAIN_EQUITY_URL.format(symbol=Symbol.upper())

        try:
            async with self._HttpSession.get(Url) as Resp:
                if Resp.status != 200:
                    Body = await Resp.text()
                    Logger.error(
                        "[%s] NSE API returned %d: %s",
                        Symbol, Resp.status, Body[:300],
                    )
                    raise RuntimeError(f"NSE returned HTTP {Resp.status}")

                Data = await Resp.json()
        except aiohttp.ContentTypeError:
            # NSE sometimes returns HTML instead of JSON (blocked)
            raise RuntimeError("NSE returned non-JSON response — cookies may be stale")

        return self._ParseNseOptionChain(Symbol, Data)

    def _ParseNseOptionChain(self, Symbol: str, Data: dict) -> list[TickRecord]:
        """
        Parse the NSE option chain JSON response into TickRecord objects.

        NSE JSON structure:
            {
                "records": {
                    "underlyingValue": 22500.0,
                    "expiryDates": ["27-Mar-2026", ...],
                    "data": [
                        {
                            "strikePrice": 22400,
                            "expiryDate": "27-Mar-2026",
                            "CE": {"lastPrice": 150.5, "openInterest": 50000, "totalTradedVolume": 12345, ...},
                            "PE": {"lastPrice": 50.2, "openInterest": 70000, "totalTradedVolume": 8000, ...}
                        },
                        ...
                    ]
                }
            }
        """
        Ticks: list[TickRecord] = []
        Now = datetime.now(timezone.utc).isoformat()

        Records = Data.get("records", {})
        UnderlyingValue = Records.get("underlyingValue", 0)
        FilteredData = Data.get("filtered", {}).get("data", [])

        # If filtered data is not available, fall back to records.data
        if not FilteredData:
            FilteredData = Records.get("data", [])

        if not FilteredData:
            # Debug: log what keys we actually received
            TopKeys = list(Data.keys())[:10]
            RecordKeys = list(Records.keys())[:10] if Records else []
            Logger.warning(
                "[%s] NSE returned empty option chain data. "
                "Top keys: %s | Record keys: %s | underlyingValue: %s",
                Symbol, TopKeys, RecordKeys, UnderlyingValue,
            )
            return []

        # Use only the nearest expiry (first in the sorted list)
        ExpiryDates = Records.get("expiryDates", [])
        NearestExpiry = ExpiryDates[0] if ExpiryDates else None

        # 1. Add the underlying (spot) tick
        if UnderlyingValue and UnderlyingValue > 0:
            Ticks.append(TickRecord(
                Timestamp=Now,
                Symbol=Symbol.upper(),
                Exchange="NSE",
                InstrumentType="EQ",
                LastPrice=float(UnderlyingValue),
                OpenInterest=0,
                Volume=0,
            ))

        # 2. Parse each strike row
        for Row in FilteredData:
            StrikePrice = Row.get("strikePrice", 0)
            RowExpiry = Row.get("expiryDate", "")

            # Only process the nearest expiry to keep data manageable
            if NearestExpiry and RowExpiry != NearestExpiry:
                continue

            # Convert NSE date format "27-Mar-2026" → "2026-03-27"
            ExpiryIso = self._ConvertNseDate(RowExpiry)

            # Parse CE (Call) data
            CeData = Row.get("CE")
            if CeData and CeData.get("lastPrice", 0) > 0:
                Ticks.append(TickRecord(
                    Timestamp=Now,
                    Symbol=Symbol.upper(),
                    Exchange="NSE",
                    InstrumentType="CE",
                    LastPrice=float(CeData.get("lastPrice", 0)),
                    OpenInterest=int(CeData.get("openInterest", 0)),
                    Volume=int(CeData.get("totalTradedVolume", 0)),
                    ExpiryDate=ExpiryIso,
                    StrikePrice=float(StrikePrice),
                ))

            # Parse PE (Put) data
            PeData = Row.get("PE")
            if PeData and PeData.get("lastPrice", 0) > 0:
                Ticks.append(TickRecord(
                    Timestamp=Now,
                    Symbol=Symbol.upper(),
                    Exchange="NSE",
                    InstrumentType="PE",
                    LastPrice=float(PeData.get("lastPrice", 0)),
                    OpenInterest=int(PeData.get("openInterest", 0)),
                    Volume=int(PeData.get("totalTradedVolume", 0)),
                    ExpiryDate=ExpiryIso,
                    StrikePrice=float(StrikePrice),
                ))

        Logger.info(
            "[%s] Parsed %d ticks from NSE (spot=%.2f, expiry=%s)",
            Symbol, len(Ticks), UnderlyingValue, NearestExpiry or "N/A",
        )
        return Ticks

    @staticmethod
    def _ConvertNseDate(NseDate: str) -> str:
        """Convert '27-Mar-2026' → '2026-03-27'."""
        if not NseDate:
            return ""
        try:
            Dt = datetime.strptime(NseDate, "%d-%b-%Y")
            return Dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            Logger.warning("Could not parse NSE date: %s", NseDate)
            return NseDate

    # ── Mock Data Generator (Fallback) ─────────────────────────

    def _GenerateMockTicks(self) -> list[TickRecord]:
        """Generate synthetic ticks for ALL watchlist symbols."""
        Ticks: list[TickRecord] = []
        for Symbol in _WATCHLIST:
            Ticks.extend(self._GenerateMockTicksForSymbol(Symbol))
        Logger.info("Generated %d mock ticks for %d symbols", len(Ticks), len(_WATCHLIST))
        return Ticks

    def _GenerateMockTicksForSymbol(self, Symbol: str) -> list[TickRecord]:
        """Generate realistic synthetic option chain ticks for a single symbol."""
        Now = datetime.now(timezone.utc)
        DaysUntilThursday = (3 - Now.weekday()) % 7
        if DaysUntilThursday == 0:
            DaysUntilThursday = 7
        Expiry = (Now + timedelta(days=DaysUntilThursday)).strftime("%Y-%m-%d")

        Ticks: list[TickRecord] = []
        BaseSpot = _MOCK_SPOT_PRICES.get(Symbol.upper(), 1000.0)
        Spot = round(BaseSpot * (1 + random.uniform(-0.005, 0.005)), 2)

        # Equity (Spot) tick
        Ticks.append(TickRecord(
            Timestamp=Now.isoformat(),
            Symbol=Symbol.upper(),
            Exchange="NSE",
            InstrumentType="EQ",
            LastPrice=Spot,
            OpenInterest=0,
            Volume=random.randint(50000, 500000),
        ))

        # Option chain ticks
        StrikeStep = _NIFTY_STRIKE_STEP if Symbol.upper() in _INDEX_SYMBOLS else _STOCK_STRIKE_STEP
        AtmStrike = round(Spot / StrikeStep) * StrikeStep

        for Offset in range(-_NUM_STRIKES_EACH_SIDE, _NUM_STRIKES_EACH_SIDE + 1):
            Strike = AtmStrike + (Offset * StrikeStep)
            if Strike <= 0:
                continue

            T = max(DaysUntilThursday / 365.0, 0.001)
            Moneyness = Spot / Strike

            for OptType in ("CE", "PE"):
                if OptType == "CE":
                    Intrinsic = max(Spot - Strike, 0)
                    OtmFactor = max(0, 1 - abs(Moneyness - 1) * 5)
                else:
                    Intrinsic = max(Strike - Spot, 0)
                    OtmFactor = max(0, 1 - abs(1/Moneyness - 1) * 5)

                TimeValue = Spot * 0.02 * math.sqrt(T) * OtmFactor
                Premium = round(max(Intrinsic + TimeValue + random.uniform(0, Spot * 0.005), 0.5), 2)

                OiBase = int(100000 * max(OtmFactor, 0.1))
                OiChange = random.randint(-int(OiBase * 0.15), int(OiBase * 0.25))

                Ticks.append(TickRecord(
                    Timestamp=Now.isoformat(),
                    Symbol=Symbol.upper(),
                    Exchange="NSE",
                    InstrumentType=OptType,
                    LastPrice=Premium,
                    OpenInterest=OiBase + OiChange,
                    Volume=random.randint(500, 50000),
                    ExpiryDate=Expiry,
                    StrikePrice=Strike,
                ))

        return Ticks

    # ── Persistence ────────────────────────────────────────────

    async def _SaveTickBatch(self, Ticks: list[TickRecord]) -> int:
        """Bulk-insert ticks into the TickData hypertable."""
        Query = """
            INSERT INTO TickData
                (Timestamp, Symbol, Exchange, InstrumentType,
                 LastPrice, OpenInterest, Volume, ExpiryDate, StrikePrice)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """
        Rows: list[tuple] = []
        for T in Ticks:
            Rows.append((
                datetime.fromisoformat(T.Timestamp),
                T.Symbol,
                T.Exchange,
                T.InstrumentType,
                T.LastPrice,
                T.OpenInterest,
                T.Volume,
                datetime.strptime(T.ExpiryDate, "%Y-%m-%d").date() if T.ExpiryDate else None,
                T.StrikePrice,
            ))

        try:
            async with self._DbPool.acquire() as Conn:
                await Conn.executemany(Query, Rows)
            return len(Rows)
        except Exception as Exc:
            Logger.error("Failed to save tick batch: %s", Exc, exc_info=True)
            return 0

    # ── Celery Dispatch ────────────────────────────────────────

    @staticmethod
    def _DispatchToDerivativesQueue(Ticks: list[TickRecord]) -> None:
        """
        Emit a single Celery task with the full tick batch so the
        MetricsComputer can process them together (micro-batching).
        """
        try:
            from app.Derivatives.Tasks import ProcessTickBatchTask

            TickDicts = [T.ToDict() for T in Ticks]
            ProcessTickBatchTask.apply_async(
                args=[TickDicts],
                queue='derivatives'
            )
            Logger.debug("Dispatched %d ticks to derivatives queue", len(TickDicts))
        except ImportError:
            Logger.warning(
                "DerivativesAnalytics.Tasks not available — skipping dispatch"
            )
        except Exception as Exc:
            Logger.error("Failed to dispatch tick batch: %s", Exc, exc_info=True)
