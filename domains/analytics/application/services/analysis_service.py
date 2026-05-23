"""
File Overview: Read-model service for the /v1/analyze endpoint. Retrieves cached snapshots from Redis (or Postgres fallback for price) and triggers background refreshes.

All Functions/Classes:
- AnalysisService: Orchestrates data retrieval for the analytical dashboard. Take data from Redis/Postgres and send to AnalysisResponse DTO.
- analyze: Main orchestrator. Take symbol from Router and send AnalysisResponse.
- _read_market_data: Take symbol and return MarketDataResponse. Take data from Redis (MARKET_PRICE) or Postgres (TickData) and send to application.
- _read_headlines: Take symbol and return list of HeadlineItem. Take data from Redis (NEWS_HEADLINES) and send to application.
- _read_sentiment: Take symbol and return SentimentResponse. Take data from Redis (SENTIMENT_AGG) and send to application.
- _read_options: Take symbol and return OptionsSummaryResponse. Take data from Redis (MARKET_OPTIONS) and send to application.
- _read_technical_forecast: Take symbol and return TechnicalForecastResponse. Take data from Redis (ML_PREDICTION) or CNN Predictor and send to application.
- _trigger_background_refresh: Take symbol and publish refresh event. Take symbol from analyze() and send to Redis Stream (ANALYSIS_REFRESH_REQUESTED).
- _log_background_task_error: Static helper to log exceptions from fire-and-forget asyncio tasks. Take exception from Task and send to logger.
- _build_freshness: Internal logic to determine data freshness. Take component timestamps and send to FreshnessMetadata.
- _parse_iso: Static utility to normalize ISO datetime strings. Take string from data sources and send to datetime object.

Endpoints/APIs:
- Consumed by /v1/analyze (Internal calling by AnalysisRouter).

Database Tables:
- TickData (Postgres), Redis (Snapshots/Cache).
"""
import json

import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional

from domains.analytics.api.schemas import (
    AnalysisResponse,
    FreshnessMetadata,
    HeadlineItem,
    MarketDataResponse,
    OptionsSummaryResponse,
    SentimentResponse,
    SentimentTimeframeData,
    TechnicalForecastResponse,
)
from shared.constants import RedisKeys, Timeframe

logger = logging.getLogger(__name__)


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
        technical_forecast = await self._read_technical_forecast(symbol_upper)

        freshness = self._build_freshness(
            market_data=market_data,
            headlines=headlines,
            sentiment=sentiment,
            options_summary=options_summary,
        )

        if freshness.stale or freshness.partial:
            task = asyncio.create_task(self._trigger_background_refresh(symbol_upper))
            task.add_done_callback(self._log_background_task_error)

        return AnalysisResponse(
            symbol=symbol_upper,
            market_data=market_data,
            headlines=headlines,
            sentiment=sentiment,
            options_summary=options_summary,
            technical_forecast=technical_forecast,
            generated_at=freshness.generated_at,
            source=freshness.source,
            stale=freshness.stale,
            partial=freshness.partial,
            status=freshness.status,
        )

    async def _read_market_data(self, symbol: str) -> Optional[MarketDataResponse]:
        try:
            from shared.infrastructure.redis_client import get_redis_client

            redis = await get_redis_client()
            cached = await redis.get(RedisKeys.MARKET_PRICE.format(symbol=symbol))
            if cached:
                payload = json.loads(cached)
                return MarketDataResponse(**payload)
        except Exception as exc:
            logger.warning("[%s] Failed reading market price cache: %s", symbol, exc)

        # Postgres read-model fallback (latest EQ tick)
        try:
            from shared.infrastructure.database import GetDatabasePool

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
                    currency="INR", # Default for Postgres read-model fallback (NSE specific)
                    market_status="CLOSED",
                    last_updated=row["timestamp"].isoformat(),
                )
        except Exception as exc:
            logger.warning("[%s] Failed reading market price from Postgres read model: %s", symbol, exc)

        return None

    async def _read_headlines(self, symbol: str) -> list[HeadlineItem]:
        try:
            from shared.infrastructure.redis_client import get_redis_client

            redis = await get_redis_client()
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
            logger.warning("[%s] Failed reading scored headlines cache: %s", symbol, exc)
            return []

    async def _read_sentiment(self, symbol: str) -> Optional[SentimentResponse]:
        try:
            from shared.infrastructure.redis_client import get_redis_client

            redis = await get_redis_client()

            tf_payloads: dict[str, dict] = {}
            for tf in Timeframe:
                key = RedisKeys.SENTIMENT_AGG.format(symbol=symbol, tf=tf.value)
                raw = await redis.get(key)
                if raw:
                    try:
                        tf_payloads[tf.value] = json.loads(raw)
                    except json.JSONDecodeError as e:
                        logger.warning("[%s] Malformed sentiment JSON for %s: %s", symbol, tf.value, e)
                else:
                    logger.info("[%s] No sentiment aggregate found in Redis for key: %s", symbol, key)

            if not tf_payloads:
                return None

            def _to_model(payload: dict) -> SentimentTimeframeData:
                # Defensive float conversion to handle explicit nulls or missing keys
                def _get_float(k: str) -> float:
                    val = payload.get(k)
                    return float(val) if val is not None else 0.0

                return SentimentTimeframeData(
                    label=payload.get("label", "NEUTRAL"),
                    avg_score=_get_float("avg_score"),
                    bullish_pct=_get_float("bullish_pct"),
                    bearish_pct=_get_float("bearish_pct"),
                    neutral_pct=_get_float("neutral_pct"),
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
            logger.error("[%s] Failed reading sentiment aggregates: %s", symbol, exc, exc_info=True)
            return None

    async def _read_options(self, symbol: str) -> Optional[OptionsSummaryResponse]:
        try:
            from domains.analytics.application.dto.read_models_dto import OptionChainSummaryDTO, compute_pcr
            from shared.infrastructure.redis_client import get_redis_client

            redis = await get_redis_client()
            cached = await redis.get(RedisKeys.MARKET_OPTIONS.format(symbol=symbol))
            if not cached:
                return OptionsSummaryResponse(available=False)

            option_chain = OptionChainSummaryDTO(**json.loads(cached)).model_dump()
            pcr_data = compute_pcr(option_chain)
            
            from domains.analytics.api.schemas import OptionTick
            raw_chain = []
            for expiry, ticks in option_chain.get("chains", {}).items():
                for t in ticks:
                    raw_chain.append(OptionTick(
                        strike=float(t.get("strike", 0.0)),
                        type=t.get("type", ""),
                        last_price=float(t.get("last_price", 0.0)),
                        iv=float(t.get("iv", 0.0)),
                        oi=int(t.get("oi", 0)),
                        volume=int(t.get("volume", 0)),
                        expiry=expiry
                    ))

            return OptionsSummaryResponse(
                pcr=float((pcr_data or {}).get("pcr", 0.0)),
                ce_volume=int((pcr_data or {}).get("ce_volume", 0)),
                pe_volume=int((pcr_data or {}).get("pe_volume", 0)),
                ce_oi=int((pcr_data or {}).get("ce_oi", 0)),
                pe_oi=int((pcr_data or {}).get("pe_oi", 0)),
                total_strikes=int(option_chain.get("summary", {}).get("total_strikes", 0)),
                expiry_dates=option_chain.get("expiry_dates", []),
                chain=raw_chain,
                available=True,
                last_updated=option_chain.get("fetched_at", ""),
            )
        except Exception as exc:
            logger.warning("[%s] Failed reading options snapshot cache: %s", symbol, exc)
            return OptionsSummaryResponse(available=False)

    async def _read_technical_forecast(self, symbol: str) -> Optional[TechnicalForecastResponse]:
        try:
            from shared.infrastructure.redis_client import get_redis_client

            redis = await get_redis_client()
            key = RedisKeys.ML_PREDICTION.format(symbol=symbol)
            cached = await redis.get(key)

            if not cached:
                # Don't block request with heavy CNN inference.
                # Background refresh (triggered by stale check) will populate this.
                logger.info("[%s] ML Cache empty (key: %s), awaiting background refresh", symbol, key)
                return None

            payload = json.loads(cached)

            return TechnicalForecastResponse(
                strategy=payload.get("strategy", "QuantCNN1D"),
                prediction=payload.get("prediction", "NEUTRAL"),
                confidence=float(payload.get("confidence", 0.0)),
                confluence_status=payload.get("confluence_status", "NEUTRAL"),
            )
        except Exception as exc:
            logger.error("[%s] Technical forecast error: %s", symbol, exc, exc_info=True)
            return None

    async def _trigger_background_refresh(self, symbol: str) -> None:
        """Fire-and-forget refresh request event to ingestion workers."""
        try:
            from shared.constants import Channels, RedisKeys, StreamGroups, Streams, TTL
            from shared.infrastructure.event_bus.contracts import AggregateUpdatedEvent, AnalysisRefreshRequestedV1
            from shared.infrastructure.event_bus.streams import DurableEventStream, StreamMessage
            from shared.infrastructure.redis_client import get_redis_client

            redis = await get_redis_client()
            stream_bus = DurableEventStream(redis)
            event = AnalysisRefreshRequestedV1(symbol=symbol, reason="stale_or_partial_read_model")
            await stream_bus.publish(Streams.ANALYSIS_REFRESH_REQUESTED, event.to_dict())
            logger.info("[%s] Published analysis refresh request event", symbol)
        except Exception as exc:
            logger.warning("[%s] Failed to publish background refresh request: %s", symbol, exc)

    @staticmethod
    def _log_background_task_error(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.warning("Background refresh task failed: %s", exc)

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

        partial = not (market_data and headlines and sentiment)
        
        # If market data is missing, we consider it "CALCULATING" or "FAILED"
        # as without price we can't do much.
        if not market_data:
            status = "CALCULATING"
        elif partial:
            status = "CALCULATING"
        else:
            status = "COMPLETED"

        stale_checks: list[bool] = []
        for component, ts in timestamps:
            age_seconds = (now - ts).total_seconds()
            stale_checks.append(age_seconds > self._STALE_SECONDS[component])

        stale = partial or (any(stale_checks) if stale_checks else True)
        
        # If very stale, might still be calculating a refresh
        if stale and status == "COMPLETED":
            status = "CALCULATING"

        return FreshnessMetadata(
            generated_at=generated_at,
            source="redis_read_model",
            stale=stale,
            partial=partial,
            status=status,
        )

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
