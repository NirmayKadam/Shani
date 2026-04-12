"""
AnomalyDetector — rule-based anomaly flagging for F&O markets.

Detects unusual derivatives activity that may signal institutional
positioning or market dislocations:
    1. OI Surge:     Single-strike OI change > 3× rolling average
    2. Volume Sweep: Total put or call volume spike > 5× trailing average

Anomalies are persisted to DetectedEvents and emitted to the
existing signals queue → AlertDispatcher → webhook pipeline.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

Logger = logging.getLogger(__name__)

# ── Thresholds ──────────────────────────────────────────────────

OI_SURGE_MULTIPLIER = 3.0       # OI change vs rolling avg
VOLUME_SWEEP_MULTIPLIER = 5.0   # volume spike vs trailing avg
MIN_OI_THRESHOLD = 5000         # ignore tiny OI values
MIN_VOLUME_THRESHOLD = 1000     # ignore illiquid strikes


class AnomalyDetector:
    """
    Stateless detector — instantiate per tick batch.
    Uses Redis for rolling averages and Postgres for event persistence.
    """

    def __init__(self) -> None:
        self._Redis = None
        self._DbPool = None

    async def _EnsureConnections(self) -> None:
        if self._Redis is None:
            from app.Infrastructure.RedisClient import GetRedisClient
            self._Redis = await GetRedisClient()
        if self._DbPool is None:
            from app.Infrastructure.DatabaseClient import GetDatabasePool
            self._DbPool = await GetDatabasePool()

    async def CheckForAnomalies(
        self, OptionTicks: list[dict], SpotMap: dict[str, float]
    ) -> list[dict]:
        """
        Main entry point. Scans a batch of option ticks for anomalies.

        Args:
            OptionTicks: list of tick dicts with InstrumentType CE/PE
            SpotMap:     dict of symbol -> current spot price

        Returns:
            List of generated anomaly event dicts (may be empty).
        """
        await self._EnsureConnections()

        Events: list[dict] = []

        # Group ticks by symbol for aggregate analysis
        BySymbol: dict[str, list[dict]] = {}
        for Tick in OptionTicks:
            Symbol = Tick.get("Symbol", "")
            if Symbol not in BySymbol:
                BySymbol[Symbol] = []
            BySymbol[Symbol].append(Tick)

        for Symbol, Ticks in BySymbol.items():
            # 1. Per-Strike OI Surge Detection
            OiEvents = await self._DetectOiSurge(Symbol, Ticks)
            Events.extend(OiEvents)

            # 2. Aggregate Volume Sweep Detection
            VolEvents = await self._DetectVolumeSweep(Symbol, Ticks)
            Events.extend(VolEvents)

        # Emit anomaly events to the signals queue
        for Event in Events:
            self._EmitToSignalsQueue(Event)

        if Events:
            Logger.info("AnomalyDetector flagged %d anomalies", len(Events))

        return Events

    # ── OI Surge Detection ─────────────────────────────────────

    async def _DetectOiSurge(self, Symbol: str, Ticks: list[dict]) -> list[dict]:
        """
        Check each strike's OI against its rolling average.
        Flag if current OI exceeds 3× the cached average.
        """
        Events: list[dict] = []

        for Tick in Ticks:
            OI = int(Tick.get("OpenInterest", 0))
            if OI < MIN_OI_THRESHOLD:
                continue

            Strike = Tick.get("StrikePrice", 0)
            OptType = Tick.get("InstrumentType", "")
            Expiry = Tick.get("ExpiryDate", "")
            CacheKey = f"anomaly:oi_avg:{Symbol}:{Strike}:{OptType}"

            # Get rolling average from Redis
            AvgStr = await self._Redis.get(CacheKey)
            if AvgStr:
                RollingAvg = float(AvgStr)
                # Update rolling average with exponential smoothing (α=0.2)
                NewAvg = 0.8 * RollingAvg + 0.2 * OI
                await self._Redis.set(CacheKey, str(round(NewAvg, 2)), ex=86400)

                # Check for surge
                if RollingAvg > 0 and OI > RollingAvg * OI_SURGE_MULTIPLIER:
                    Headline = (
                        f"{Symbol} {OptType} {Strike} OI surged to {OI:,} "
                        f"({OI/RollingAvg:.1f}× rolling average of {RollingAvg:,.0f})"
                    )
                    Event = await self._PersistEvent(
                        Symbol, "OI_SURGE", Headline, OI / RollingAvg
                    )
                    if Event:
                        Events.append(Event)
            else:
                # First observation — seed the rolling average
                await self._Redis.set(CacheKey, str(float(OI)), ex=86400)

        return Events

    # ── Volume Sweep Detection ─────────────────────────────────

    async def _DetectVolumeSweep(self, Symbol: str, Ticks: list[dict]) -> list[dict]:
        """
        Check if total CE or PE volume in this batch is an outlier
        relative to the trailing average.
        """
        Events: list[dict] = []

        CeVol = sum(int(t.get("Volume", 0)) for t in Ticks if t.get("InstrumentType") == "CE")
        PeVol = sum(int(t.get("Volume", 0)) for t in Ticks if t.get("InstrumentType") == "PE")

        for Label, CurrentVol in [("CE", CeVol), ("PE", PeVol)]:
            if CurrentVol < MIN_VOLUME_THRESHOLD:
                continue

            CacheKey = f"anomaly:vol_avg:{Symbol}:{Label}"
            AvgStr = await self._Redis.get(CacheKey)

            if AvgStr:
                RollingAvg = float(AvgStr)
                NewAvg = 0.8 * RollingAvg + 0.2 * CurrentVol
                await self._Redis.set(CacheKey, str(round(NewAvg, 2)), ex=86400)

                if RollingAvg > 0 and CurrentVol > RollingAvg * VOLUME_SWEEP_MULTIPLIER:
                    Headline = (
                        f"{Symbol} {Label} volume sweep: {CurrentVol:,} "
                        f"({CurrentVol/RollingAvg:.1f}× trailing average of {RollingAvg:,.0f})"
                    )
                    Event = await self._PersistEvent(
                        Symbol, "VOLUME_SWEEP", Headline, CurrentVol / RollingAvg
                    )
                    if Event:
                        Events.append(Event)
            else:
                await self._Redis.set(CacheKey, str(float(CurrentVol)), ex=86400)

        return Events

    # ── Persistence & Dispatch ─────────────────────────────────

    async def _PersistEvent(
        self, Symbol: str, EventType: str, Headline: str, Confidence: float
    ) -> Optional[dict]:
        """Insert anomaly into DetectedEvents table and return event dict."""
        try:
            Query = """
                INSERT INTO DetectedEvents
                    (Symbol, EventType, Headline, SourceType, Confidence)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING EventId
            """
            EventId = await self._DbPool.fetchval(
                Query, Symbol, EventType, Headline, "DERIVATIVES", min(Confidence / 10, 1.0)
            )
            Logger.info("🚨 ANOMALY: %s", Headline)
            return {
                "event_id": str(EventId),
                "symbol": Symbol,
                "event_type": EventType,
                "headline": Headline,
            }
        except Exception as Exc:
            Logger.error("Failed to persist anomaly event: %s", Exc, exc_info=True)
            return None

    @staticmethod
    def _EmitToSignalsQueue(Event: dict) -> None:
        """Push anomaly into the existing signals pipeline for webhook dispatch."""
        try:
            from app.NewsSentiment.SignalTasks import DispatchAlertTask
            DispatchAlertTask.apply_async(args=[Event], queue='signals')
            Logger.debug("Emitted anomaly alert for %s", Event.get("symbol"))
        except ImportError:
            Logger.warning("MarketSignals.Tasks not available — skipping alert dispatch")
        except Exception as Exc:
            Logger.error("Failed to emit anomaly alert: %s", Exc, exc_info=True)
