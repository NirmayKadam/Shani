"""
MetricsComputer — quantitative F&O analytics engine.

Processes raw tick data to compute:
    1. Put-Call Ratio (PCR) per symbol/expiry
    2. Implied Volatility (IV) per strike using BSM + SciPy root-finding
    3. Caches results in Redis for sub-millisecond API reads

Called by the DerivativesAnalytics Celery task whenever a tick batch
arrives from the ingestion layer.
"""

import math
import logging
from datetime import datetime, timezone
from typing import Optional

from scipy import optimize
from scipy.stats import norm

Logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────

RISK_FREE_RATE = 0.065          # 6.5% (RBI T-Bill proxy)
IV_SOLVER_LOWER = 0.01          # 1% vol floor
IV_SOLVER_UPPER = 5.0           # 500% vol ceiling
IV_SOLVER_TOLERANCE = 1e-6      # solver convergence tolerance
IV_CACHE_TTL = 300              # 5 minutes
PCR_CACHE_TTL = 300             # 5 minutes


# ── Black-Scholes-Merton Helpers ────────────────────────────────

def BsmPrice(
    S: float, K: float, T: float, r: float, sigma: float,
    OptionType: str = "CE"
) -> float:
    """
    Black-Scholes-Merton option pricing (European, no dividends).

    Args:
        S:      Spot price
        K:      Strike price
        T:      Time to expiry in years
        r:      Risk-free rate
        sigma:  Volatility
        OptionType: 'CE' for Call, 'PE' for Put

    Returns:
        Theoretical option price
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return max(S - K, 0) if OptionType == "CE" else max(K - S, 0)

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    if OptionType == "CE":
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    else:
        return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def CorradoMillerIV(
    S: float, K: float, T: float, r: float, MarketPrice: float,
    OptionType: str = "CE"
) -> float:
    """
    Corrado-Miller closed-form IV approximation — used as fallback
    when the numerical solver fails to converge.

    Returns an approximate implied volatility.
    """
    if T <= 0 or S <= 0 or K <= 0:
        return 0.0

    Fwd = S * math.exp(r * T)
    Diff = Fwd - K
    C = MarketPrice * math.exp(r * T)  # forward option price

    try:
        Inner = (C - Diff / 2) ** 2 - (Diff ** 2) / math.pi
        if Inner < 0:
            Inner = 0
        Sigma = (1 / math.sqrt(T)) * (
            math.sqrt(2 * math.pi) / (S + K)
        ) * (C - Diff / 2 + math.sqrt(Inner))
        return max(Sigma, 0.01)
    except (ValueError, ZeroDivisionError):
        return 0.20  # reasonable default


# ── MetricsComputer ─────────────────────────────────────────────

class MetricsComputer:
    """
    Stateless compute engine — instantiate per task invocation.
    All state is persisted to Redis/Postgres, never held in memory.
    """

    def __init__(self) -> None:
        self._Redis = None
        self._DbPool = None

    async def _EnsureConnections(self) -> None:
        """Lazy-init shared infrastructure connections."""
        if self._Redis is None:
            from app.Infrastructure.RedisClient import GetRedisClient
            self._Redis = await GetRedisClient()
        if self._DbPool is None:
            from app.Infrastructure.DatabaseClient import GetDatabasePool
            self._DbPool = await GetDatabasePool()

    # ── Main Entry Point ───────────────────────────────────────

    async def ProcessTickBatch(self, TickDicts: list[dict]) -> dict:
        """
        Process a batch of raw tick dicts from the ingestion layer.

        1. Extracts spot prices for each symbol
        2. Computes PCR per symbol/expiry
        3. Computes IV per option strike
        4. Caches everything to Redis
        5. Runs anomaly detection

        Returns a summary dict for logging.
        """
        await self._EnsureConnections()

        if not TickDicts:
            return {"processed": 0}

        # Separate ticks by type
        SpotMap: dict[str, float] = {}          # symbol -> spot price
        OptionTicks: list[dict] = []

        for Tick in TickDicts:
            Symbol = Tick.get("Symbol", "")
            InstType = Tick.get("InstrumentType", "")

            if InstType == "EQ":
                SpotMap[Symbol] = float(Tick.get("LastPrice", 0))
            elif InstType in ("CE", "PE"):
                OptionTicks.append(Tick)

        # Group options by (symbol, expiry) for PCR calculation
        PcrGroups: dict[tuple[str, str], dict] = {}
        for Tick in OptionTicks:
            Symbol = Tick.get("Symbol", "")
            Expiry = Tick.get("ExpiryDate", "")
            Key = (Symbol, Expiry)

            if Key not in PcrGroups:
                PcrGroups[Key] = {"CE_Volume": 0, "PE_Volume": 0, "CE_OI": 0, "PE_OI": 0}

            InstType = Tick["InstrumentType"]
            Vol = int(Tick.get("Volume", 0))
            OI = int(Tick.get("OpenInterest", 0))

            if InstType == "CE":
                PcrGroups[Key]["CE_Volume"] += Vol
                PcrGroups[Key]["CE_OI"] += OI
            else:
                PcrGroups[Key]["PE_Volume"] += Vol
                PcrGroups[Key]["PE_OI"] += OI

        # 1. Compute and cache PCR
        PcrResults: dict[str, float] = {}
        for (Symbol, Expiry), Counts in PcrGroups.items():
            Pcr = self._ComputePCR(Counts)
            PcrResults[f"{Symbol}:{Expiry}"] = Pcr
            await self._CachePCR(Symbol, Expiry, Pcr, Counts)

        # 2. Compute and cache IV for each option tick
        IvCount = 0
        IvSurfaces: dict[str, list[dict]] = {}  # symbol -> [{strike, iv, type}]

        for Tick in OptionTicks:
            Symbol = Tick.get("Symbol", "")
            Spot = SpotMap.get(Symbol)
            if not Spot:
                continue

            Strike = float(Tick.get("StrikePrice", 0))
            MarketPrice = float(Tick.get("LastPrice", 0))
            Expiry = Tick.get("ExpiryDate", "")
            OptType = Tick.get("InstrumentType", "CE")

            if Strike <= 0 or MarketPrice <= 0:
                continue

            # Time to expiry in years
            T = self._TimeToExpiry(Expiry)
            if T <= 0:
                continue

            Iv = self._ComputeIV(MarketPrice, Spot, Strike, T, RISK_FREE_RATE, OptType)

            if Iv and Iv > 0:
                await self._CacheIV(Symbol, Strike, Expiry, OptType, Iv)
                IvCount += 1

                if Symbol not in IvSurfaces:
                    IvSurfaces[Symbol] = []
                IvSurfaces[Symbol].append({
                    "strike": Strike,
                    "iv": round(Iv, 4),
                    "type": OptType,
                    "expiry": Expiry,
                })

        # Cache full IV surface per symbol for API reads
        import json
        for Symbol, Surface in IvSurfaces.items():
            CacheKey = f"derivatives:iv_surface:{Symbol}"
            await self._Redis.set(CacheKey, json.dumps(Surface), ex=IV_CACHE_TTL)

        # 3. Run anomaly detection
        from app.Derivatives.Anomalies.AnomalyDetector import AnomalyDetector
        Detector = AnomalyDetector()
        await Detector.CheckForAnomalies(OptionTicks, SpotMap)

        Summary = {
            "processed": len(TickDicts),
            "spots": len(SpotMap),
            "pcr_groups": len(PcrResults),
            "iv_computed": IvCount,
        }
        Logger.info("MetricsComputer summary: %s", Summary)
        return Summary

    # ── PCR Calculation ────────────────────────────────────────

    @staticmethod
    def _ComputePCR(Counts: dict) -> float:
        """
        Put-Call Ratio based on volume.
        PCR > 1 = bearish, PCR < 1 = bullish.
        """
        CeVol = Counts.get("CE_Volume", 0)
        if CeVol == 0:
            return 0.0
        return round(Counts.get("PE_Volume", 0) / CeVol, 4)

    async def _CachePCR(self, Symbol: str, Expiry: str, Pcr: float, Counts: dict) -> None:
        """Cache PCR and volume breakdown in Redis."""
        import json
        CacheKey = f"derivatives:pcr:{Symbol}"
        Payload = {
            "symbol": Symbol,
            "expiry": Expiry,
            "pcr": Pcr,
            "ce_volume": Counts["CE_Volume"],
            "pe_volume": Counts["PE_Volume"],
            "ce_oi": Counts["CE_OI"],
            "pe_oi": Counts["PE_OI"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._Redis.set(CacheKey, json.dumps(Payload), ex=PCR_CACHE_TTL)
        Logger.debug("[%s] PCR cached: %.4f", Symbol, Pcr)

    # ── IV Calculation ─────────────────────────────────────────

    @staticmethod
    def _ComputeIV(
        MarketPrice: float, Spot: float, Strike: float,
        T: float, r: float, OptionType: str
    ) -> Optional[float]:
        """
        Back-calculate Implied Volatility using Brent's method.
        Falls back to Corrado-Miller approximation if solver diverges.
        """
        # Objective: find sigma such that BSM(sigma) = MarketPrice
        def Objective(sigma: float) -> float:
            return BsmPrice(Spot, Strike, T, r, sigma, OptionType) - MarketPrice

        try:
            # Check that the bracket contains a root
            LowVal = Objective(IV_SOLVER_LOWER)
            HighVal = Objective(IV_SOLVER_UPPER)

            if LowVal * HighVal > 0:
                # No sign change — solver won't converge, use fallback
                return CorradoMillerIV(Spot, Strike, T, r, MarketPrice, OptionType)

            Iv = optimize.brentq(
                Objective,
                IV_SOLVER_LOWER,
                IV_SOLVER_UPPER,
                xtol=IV_SOLVER_TOLERANCE,
                maxiter=100,
            )
            return round(Iv, 6)

        except (ValueError, RuntimeError) as Exc:
            Logger.debug(
                "IV solver failed for S=%.2f K=%.2f T=%.4f Type=%s: %s — using fallback",
                Spot, Strike, T, OptionType, Exc,
            )
            return CorradoMillerIV(Spot, Strike, T, r, MarketPrice, OptionType)

    async def _CacheIV(
        self, Symbol: str, Strike: float, Expiry: str, OptType: str, Iv: float
    ) -> None:
        """Cache individual strike IV in Redis."""
        CacheKey = f"derivatives:iv:{Symbol}:{Strike}:{Expiry}:{OptType}"
        await self._Redis.set(CacheKey, str(round(Iv, 6)), ex=IV_CACHE_TTL)

    # ── Helpers ────────────────────────────────────────────────

    @staticmethod
    def _TimeToExpiry(ExpiryStr: str) -> float:
        """
        Calculate time to expiry in years from an expiry date string.
        Returns 0 if the option has already expired.
        """
        if not ExpiryStr:
            return 0.0
        try:
            ExpiryDate = datetime.strptime(ExpiryStr, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            Now = datetime.now(timezone.utc)
            Delta = (ExpiryDate - Now).total_seconds()
            return max(Delta / (365.25 * 24 * 3600), 0.0)
        except (ValueError, TypeError):
            return 0.0
