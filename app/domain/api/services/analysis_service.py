import json
import logging
from datetime import datetime, timezone
from typing import Optional

from app.domain.api.schemas import (
    AnalysisResponse,
    FreshnessMetadata,
    HeadlineItem,
    MarketDataResponse,
    OptionsSummaryResponse,
    SentimentResponse,
    SentimentTimeframeData,
)
from app.shared.constants import RedisKeys, Timeframe

Logger = logging.getLogger(__name__)


class AnalysisService:
    """Read-model service for /v1/analyze.

    The API path is intentionally cache-first and non-blocking:
    - Reads latest cached snapshot from Redis (with Postgres fallback for market price).
    - Returns freshness metadata so clients can reason about staleness/partial responses.
    - Triggers an async refresh command for stale or partial snapshots.
    """

    _STALE_SECONDS = {
        "market": 90,
        "headlines": 10 * 60,
        "options": 3 * 60,
        "sentiment": 6 * 60,
    }

    async def analyze(self, symbol: str) -> AnalysisResponse:
        symbol_upper = symbol.upper()

        market_data = await self._read_market_data(symbol_upper)
        headlines = await self._read_headlines(symbol_upper)
        sentiment = await self._read_sentiment(symbol_upper)
        options_summary = await self._read_options(symbol_upper)

        freshness = self._build_freshness(
            market_data=market_data,
            headlines=headlines,
            sentiment=sentiment,
            options_summary=options_summary,
        )

        if freshness.stale or freshness.partial:
            await self._trigger_background_refresh(symbol_upper)

        return AnalysisResponse(
            symbol=symbol_upper,
            market_data=market_data,
            headlines=headlines,
            sentiment=sentiment,
            options_summary=options_summary,
            technical_forecast=None,
            generated_at=freshness.generated_at,
            stale=freshness.stale,
            partial=freshness.partial,
        )

    async def _read_market_data(self, symbol: str) -> Optional[MarketDataResponse]:
        try:
            from app.shared.redis_client import GetRedisClient

            redis = await GetRedisClient()
            cached = await redis.get(RedisKeys.MARKET_PRICE.format(symbol=symbol))
            if cached:
                payload = json.loads(cached)
                return MarketDataResponse(**payload)
        except Exception as exc:
            Logger.warning("[%s] Failed reading market price cache: %s", symbol, exc)

        # Postgres read-model fallback (latest EQ tick)
        try:
            from app.shared.database import GetDatabasePool

            db_pool = await GetDatabasePool()
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT Timestamp, LastPrice, Volume
                    FROM TickData
                    WHERE Symbol = $1 AND InstrumentType = 'EQ'
                    ORDER BY Timestamp DESC
                    LIMIT 1
                    """,
                    symbol,
                )

            if row:
                return MarketDataResponse(
                    last_price=float(row["lastprice"] or 0.0),
                    open=float(row["lastprice"] or 0.0),
                    high=float(row["lastprice"] or 0.0),
                    low=float(row["lastprice"] or 0.0),
                    volume=int(row["volume"] or 0),
                    previous_close=float(row["lastprice"] or 0.0),
                    change_percent=0.0,
                    market_status="CLOSED",
                    last_updated=row["timestamp"].isoformat(),
                )
        except Exception as exc:
            Logger.warning("[%s] Failed reading market price from Postgres read model: %s", symbol, exc)

        return None

    async def _read_headlines(self, symbol: str) -> list[HeadlineItem]:
        try:
            from app.shared.redis_client import GetRedisClient

            redis = await GetRedisClient()
            cached_items = await redis.zrevrange(RedisKeys.NEWS_HEADLINES.format(symbol=symbol), 0, 19)
            if not cached_items:
                return []

            items: list[HeadlineItem] = []
            for item in cached_items:
                h = json.loads(item)
                items.append(
                    HeadlineItem(
                        headline=h.get("headline", ""),
                        source_name=h.get("source_name", ""),
                        published_at=h.get("published_at", ""),
                        sentiment_label=h.get("sentiment_label", "NEUTRAL"),
                        sentiment_score=float(h.get("sentiment_score", 0.0)),
                        confidence=float(h.get("confidence", 0.0)),
                    )
                )
            return items
        except Exception as exc:
            Logger.warning("[%s] Failed reading scored headlines cache: %s", symbol, exc)
            return []

    async def _read_sentiment(self, symbol: str) -> Optional[SentimentResponse]:
        try:
            from app.shared.redis_client import GetRedisClient

            redis = await GetRedisClient()

            tf_payloads: dict[str, dict] = {}
            for tf in Timeframe:
                raw = await redis.get(RedisKeys.SENTIMENT_AGG.format(symbol=symbol, tf=tf.value))
                if raw:
                    tf_payloads[tf.value] = json.loads(raw)

            if not tf_payloads:
                return None

            def _to_model(payload: dict) -> SentimentTimeframeData:
                return SentimentTimeframeData(
                    label=payload.get("label", "NEUTRAL"),
                    avg_score=float(payload.get("avg_score", 0.0)),
                    bullish_pct=float(payload.get("bullish_pct", 0.0)),
                    bearish_pct=float(payload.get("bearish_pct", 0.0)),
                    neutral_pct=float(payload.get("neutral_pct", 0.0)),
                    count=int(payload.get("count", 0)),
                    trend=payload.get("trend", "STABLE"),
                )

            return SentimentResponse(
                intraday=_to_model(tf_payloads.get("intraday", {})),
                daily=_to_model(tf_payloads.get("daily", {})),
                weekly=_to_model(tf_payloads.get("weekly", {})),
                monthly=_to_model(tf_payloads.get("monthly", {})),
            )
        except Exception as exc:
            Logger.warning("[%s] Failed reading sentiment aggregates cache: %s", symbol, exc)
            return None

    async def _read_options(self, symbol: str) -> Optional[OptionsSummaryResponse]:
        try:
            from app.domain.api.read_models import OptionChainSummaryReadModel, compute_pcr
            from app.shared.redis_client import GetRedisClient

            redis = await GetRedisClient()
            cached = await redis.get(RedisKeys.MARKET_OPTIONS.format(symbol=symbol))
            if not cached:
                return OptionsSummaryResponse(available=False)

            option_chain = OptionChainSummaryReadModel(**json.loads(cached)).model_dump()
            pcr_data = compute_pcr(option_chain)
            return OptionsSummaryResponse(
                pcr=float((pcr_data or {}).get("pcr", 0.0)),
                ce_volume=int((pcr_data or {}).get("ce_volume", 0)),
                pe_volume=int((pcr_data or {}).get("pe_volume", 0)),
                ce_oi=int((pcr_data or {}).get("ce_oi", 0)),
                pe_oi=int((pcr_data or {}).get("pe_oi", 0)),
                total_strikes=int(option_chain.get("summary", {}).get("total_strikes", 0)),
                expiry_dates=option_chain.get("expiry_dates", []),
                available=True,
                last_updated=option_chain.get("fetched_at", ""),
            )
        except Exception as exc:
            Logger.warning("[%s] Failed reading options snapshot cache: %s", symbol, exc)
            return OptionsSummaryResponse(available=False)

    async def _trigger_background_refresh(self, symbol: str) -> None:
        """Fire-and-forget refresh command to ingestion workers."""
        try:
            from app.celery_app import CeleryApp

            CeleryApp.send_task("ingestion.refresh_symbol", args=[symbol])
            Logger.info("[%s] Enqueued background refresh task", symbol)
        except Exception as exc:
            Logger.warning("[%s] Failed to enqueue background refresh: %s", symbol, exc)

    def _build_freshness(
        self,
        *,
        market_data: Optional[MarketDataResponse],
        headlines: list[HeadlineItem],
        sentiment: Optional[SentimentResponse],
        options_summary: Optional[OptionsSummaryResponse],
    ) -> FreshnessMetadata:
        now = datetime.now(timezone.utc)

        timestamps: list[tuple[str, datetime]] = []

        market_dt = self._parse_iso(market_data.last_updated) if market_data else None
        if market_dt:
            timestamps.append(("market", market_dt))

        headlines_dt = self._parse_iso(headlines[0].published_at) if headlines else None
        if headlines_dt:
            timestamps.append(("headlines", headlines_dt))

        options_dt = (
            self._parse_iso(options_summary.last_updated)
            if options_summary and options_summary.available
            else None
        )
        if options_dt:
            timestamps.append(("options", options_dt))

        # Sentiment aggregates don't include a computed_at field today.
        # Infer recency from newest headline when aggregates are present.
        if sentiment and headlines_dt:
            timestamps.append(("sentiment", headlines_dt))

        generated_at_dt = max((ts for _, ts in timestamps), default=None)
        generated_at = generated_at_dt.isoformat() if generated_at_dt else ""

        partial = not (market_data and headlines and sentiment and options_summary and options_summary.available)

        stale_checks: list[bool] = []
        for component, ts in timestamps:
            age_seconds = (now - ts).total_seconds()
            stale_checks.append(age_seconds > self._STALE_SECONDS[component])

        stale = partial or (any(stale_checks) if stale_checks else True)

        return FreshnessMetadata(generated_at=generated_at, stale=stale, partial=partial)

    @staticmethod
    def _parse_iso(value: str) -> Optional[datetime]:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (TypeError, ValueError):
            return None
