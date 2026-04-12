# app/domain/api/services/analysis_service.py — On-demand analysis orchestrator
#
# This is the core service that ties together:
#   1. Market data fetch (yfinance)
#   2. News headlines fetch (NewsAPI)
#   3. FinBERT sentiment scoring
#   4. Multi-timeframe aggregation
#   5. Option chain fetch + PCR computation
#
# Does NOT cross domain boundaries via imports — it uses the shared
# infrastructure and domain classes that are designed for on-demand use.

import json
import logging
from typing import Optional

from app.shared.constants import RedisKeys, TTL
from app.domain.api.schemas import (
    AnalysisResponse,
    MarketDataResponse,
    HeadlineItem,
    SentimentResponse,
    SentimentTimeframeData,
    OptionsSummaryResponse,
)

Logger = logging.getLogger(__name__)


class AnalysisService:
    """
    Stateless orchestrator for on-demand symbol analysis.

    Usage:
        service = AnalysisService()
        response = await service.analyze("NIFTY")
    """

    async def analyze(self, symbol: str) -> AnalysisResponse:
        """
        Full on-demand analysis pipeline:
          1. Fetch market data via yfinance
          2. Fetch latest 20 headlines from NewsAPI
          3. Score all headlines with FinBERT
          4. Compute multi-timeframe aggregates
          5. Fetch option chain from NSE + compute PCR
          6. Return consolidated response

        Never raises — returns partial data on failures. Never returns blank.
        """
        symbol_upper = symbol.upper()

        # ── 1. Fetch Market Data ──
        market_data = await self._fetch_market_data(symbol_upper)

        # ── 2. Fetch + Score Headlines ──
        scored_headlines = await self._fetch_and_score_headlines(symbol_upper)

        # ── 3. Compute Multi-Timeframe Sentiment ──
        sentiment = self._compute_sentiment(scored_headlines)

        # ── 4. Fetch Options + Compute PCR ──
        options_summary = await self._fetch_options(symbol_upper)

        # ── 5. Cache results for WebSocket/future reads ──
        await self._cache_results(symbol_upper, scored_headlines, market_data)

        # ── 5b. CNN Technical Forecast Confluence ──
        technical_forecast = None
        try:
            import asyncio
            from app.domain.forecasting.inference import InferenceEngine
            
            engine = InferenceEngine.get_instance()
            if engine.is_loaded:
                # We extract the latest LIVE sentiment score (or 0 if neutral) to feed the ML
                live_sentiment_score = 0.0
                live_sentiment_label = "NEUTRAL"
                if sentiment and sentiment.monthly:
                    live_sentiment_score = sentiment.monthly.avg_score
                    live_sentiment_label = sentiment.monthly.label
                
                # Execute PyTorch inference securely off the main thread to prevent event-loop blocking
                technical_forecast = await asyncio.to_thread(
                    engine.predict,
                    symbol_upper,
                    live_sentiment_label,
                    live_sentiment_score
                )
        except Exception as exc:
            Logger.error("[%s] Failed executing CNN Confluence: %s", symbol_upper, exc)

        # ── 6. Build Response ──
        headline_items = [
            HeadlineItem(
                headline=h.get("headline", ""),
                source_name=h.get("source_name", ""),
                published_at=h.get("published_at", ""),
                sentiment_label=h.get("sentiment_label", "NEUTRAL"),
                sentiment_score=h.get("sentiment_score", 0.0),
                confidence=h.get("confidence", 0.0),
            )
            for h in scored_headlines
        ]

        return AnalysisResponse(
            symbol=symbol_upper,
            market_data=market_data,
            headlines=headline_items,
            sentiment=sentiment,
            options_summary=options_summary,
            technical_forecast=technical_forecast,
        )

    # ── Internal Methods ───────────────────────────────────────

    async def _fetch_market_data(self, symbol: str) -> Optional[MarketDataResponse]:
        """Fetch via yfinance, falling back to Redis cache."""
        try:
            # Try fresh fetch
            from app.domain.ingestion.market_data_fetcher import MarketPriceFetcher
            fetcher = MarketPriceFetcher()
            data = await fetcher.fetch(symbol)

            if data:
                return MarketDataResponse(**data)

        except Exception as exc:
            Logger.warning("[%s] yfinance fetch failed: %s — trying cache", symbol, exc)

        # Fall back to Redis cache
        try:
            from app.shared.redis_client import GetRedisClient
            redis = await GetRedisClient()
            cache_key = RedisKeys.MARKET_PRICE.format(symbol=symbol)
            cached = await redis.get(cache_key)

            if cached:
                data = json.loads(cached)
                data["market_status"] = "CLOSED"  # Override since it's cached
                return MarketDataResponse(**data)
        except Exception as exc:
            Logger.error("[%s] Redis cache read also failed: %s", symbol, exc)

        return None

    async def _fetch_and_score_headlines(self, symbol: str) -> list[dict]:
        """Fetch headlines from NewsAPI and score with FinBERT."""

        # 1. Try fetching fresh headlines
        headlines: list[dict] = []
        try:
            from app.domain.ingestion.news_fetcher import NewsFetcher
            from app.config import GetSettings

            cfg = GetSettings()
            fetcher = NewsFetcher(api_key=cfg.NewsApiKey)
            headlines = await fetcher.fetch(symbol, max_results=20)
            await fetcher.close()
        except Exception as exc:
            Logger.warning("[%s] NewsAPI fetch failed: %s — trying cache", symbol, exc)

        # 2. If no fresh headlines, try Redis cache
        if not headlines:
            try:
                from app.shared.redis_client import GetRedisClient
                redis = await GetRedisClient()
                cache_key = RedisKeys.NEWS_HEADLINES.format(symbol=symbol)
                # Get latest 20 from sorted set (highest scores = most recent)
                cached_items = await redis.zrevrange(cache_key, 0, 19)
                if cached_items:
                    headlines = [json.loads(item) for item in cached_items]
                    Logger.info("[%s] Loaded %d cached headlines", symbol, len(headlines))
                    return headlines  # Already scored
            except Exception as exc:
                Logger.warning("[%s] Redis headline cache read failed: %s", symbol, exc)

        if not headlines:
            Logger.warning("[%s] No headlines available from any source", symbol)
            return []

        # 3. Score with FinBERT
        try:
            from app.domain.sentiment.analyzer import SentimentAnalyzer
            analyzer = SentimentAnalyzer()
            scored = await analyzer.score_headlines(headlines)
            return scored
        except Exception as exc:
            Logger.error("[%s] FinBERT scoring failed: %s", symbol, exc)
            # Return unscored headlines with default NEUTRAL labels
            return [
                {**h, "sentiment_label": "NEUTRAL", "sentiment_score": 0.0, "confidence": 0.0}
                for h in headlines
            ]

    @staticmethod
    def _compute_sentiment(scored_headlines: list[dict]) -> Optional[SentimentResponse]:
        """Compute multi-timeframe aggregates from scored headlines."""
        if not scored_headlines:
            return None

        try:
            from app.domain.sentiment.timeframes import TimeframeComputer
            computer = TimeframeComputer()
            tf_data = computer.compute_all(scored_headlines)

            # Convert to response model
            def _to_model(data: dict) -> SentimentTimeframeData:
                return SentimentTimeframeData(
                    label=data.get("label", "NEUTRAL"),
                    avg_score=data.get("avg_score", 0.0),
                    bullish_pct=data.get("bullish_pct", 0.0),
                    bearish_pct=data.get("bearish_pct", 0.0),
                    neutral_pct=data.get("neutral_pct", 0.0),
                    count=data.get("count", 0),
                    trend=data.get("trend", "STABLE"),
                )

            return SentimentResponse(
                intraday=_to_model(tf_data.get("intraday", {})),
                daily=_to_model(tf_data.get("daily", {})),
                weekly=_to_model(tf_data.get("weekly", {})),
                monthly=_to_model(tf_data.get("monthly", {})),
            )
        except Exception as exc:
            Logger.error("Multi-timeframe computation failed: %s", exc)
            return None

    async def _fetch_options(self, symbol: str) -> Optional[OptionsSummaryResponse]:
        """Fetch option chain and compute PCR."""

        option_chain: Optional[dict] = None

        # 1. Try fresh fetch from NSE
        try:
            from app.domain.ingestion.market_data_fetcher import OptionChainFetcher
            fetcher = OptionChainFetcher()
            await fetcher.initialise()
            option_chain = await fetcher.fetch(symbol)
            await fetcher.close()
        except Exception as exc:
            Logger.warning("[%s] NSE option chain fetch failed: %s — trying cache", symbol, exc)

        # 2. Fall back to Redis cache
        if not option_chain:
            try:
                from app.shared.redis_client import GetRedisClient
                redis = await GetRedisClient()
                cache_key = RedisKeys.MARKET_OPTIONS.format(symbol=symbol)
                cached = await redis.get(cache_key)
                if cached:
                    option_chain = json.loads(cached)
            except Exception as exc:
                Logger.warning("[%s] Redis option cache read failed: %s", symbol, exc)

        if not option_chain:
            return OptionsSummaryResponse(available=False)

        # 3. Compute PCR
        try:
            from app.domain.sentiment.analyzer import SentimentAnalyzer
            pcr_data = SentimentAnalyzer.compute_pcr(option_chain)

            return OptionsSummaryResponse(
                pcr=pcr_data["pcr"] if pcr_data else 0.0,
                ce_volume=pcr_data["ce_volume"] if pcr_data else 0,
                pe_volume=pcr_data["pe_volume"] if pcr_data else 0,
                ce_oi=pcr_data["ce_oi"] if pcr_data else 0,
                pe_oi=pcr_data["pe_oi"] if pcr_data else 0,
                total_strikes=option_chain.get("summary", {}).get("total_strikes", 0),
                expiry_dates=option_chain.get("expiry_dates", []),
                available=True,
                last_updated=option_chain.get("fetched_at", ""),
            )
        except Exception as exc:
            Logger.error("[%s] PCR computation failed: %s", symbol, exc)
            return OptionsSummaryResponse(available=False)

    async def _cache_results(
        self, symbol: str, scored_headlines: list[dict], market_data
    ) -> None:
        """Cache scored headlines and market data in Redis for WebSocket consumers."""
        try:
            from app.shared.redis_client import GetRedisClient
            redis = await GetRedisClient()

            # Cache scored headlines in sorted set
            if scored_headlines:
                key = RedisKeys.NEWS_HEADLINES.format(symbol=symbol)
                pipe = redis.pipeline()
                for h in scored_headlines:
                    ts = self._parse_ts(h.get("published_at", ""))
                    pipe.zadd(key, {json.dumps(h, default=str): ts})
                pipe.zremrangebyrank(key, 0, -51)  # Keep latest 50
                pipe.expire(key, TTL.HEADLINES)
                await pipe.execute()

            # Cache market data
            if market_data:
                key = RedisKeys.MARKET_PRICE.format(symbol=symbol)
                await redis.set(key, json.dumps(market_data.model_dump(), default=str), ex=TTL.MARKET_PRICE)

        except Exception as exc:
            Logger.warning("[%s] Failed to cache results: %s", symbol, exc)

    @staticmethod
    def _parse_ts(ts_str: str) -> float:
        from datetime import datetime, timezone
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            return dt.timestamp()
        except (ValueError, TypeError):
            return datetime.now(timezone.utc).timestamp()
