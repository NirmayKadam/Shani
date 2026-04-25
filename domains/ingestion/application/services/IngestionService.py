import json
import logging
from datetime import datetime, timezone

from domains.ingestion.infrastructure.adapters.outbound.NewsApiAdapter import NewsApiAdapter, NewsFetcher
from domains.ingestion.infrastructure.adapters.outbound.NseApiAdapter import NseApiAdapter, MarketPriceFetcher, OptionChainFetcher
from domains.ingestion.infrastructure.adapters.outbound.RedisDedupAdapter import RedisDedupAdapter
from domains.ingestion.infrastructure.adapters.outbound.RedisEventBusAdapter import RedisEventBusAdapter
from shared.constants import RedisKeys, Streams, TTL

Logger = logging.getLogger(__name__)


class IngestionService:
    """Orchestrates news, price, and options ingestion.

    Uses sync Redis (runs inside Celery workers).
    """

    def __init__(
        self,
        news_fetcher: NewsFetcher,
        price_fetcher: MarketPriceFetcher,
        option_fetcher: OptionChainFetcher,
        redis_client,
        event_bus: RedisEventBusAdapter,
    ):
        self._news = news_fetcher
        self._price = price_fetcher
        self._option = option_fetcher
        self._redis = redis_client
        self._bus = event_bus

    # ── News ────────────────────────────────────────────────────

    async def ingest_news(self, symbol: str) -> None:
        try:
            headlines = await self._news.fetch(symbol)
        except Exception as e:
            Logger.error("[%s] Failed to fetch news: %s", symbol, e)
            return

        if not headlines:
            Logger.info("[%s] No headlines fetched", symbol)
            return

        count = 0
        for h in headlines:
            url = h.get("source_url", "")
            dedup_key = f"news:seen:{hash(url) & 0xFFFFFFFF:08x}"

            if self._redis.exists(dedup_key):
                continue

            # Build event payload matching HeadlineFetchedV1 contract
            event_payload = {
                "event_type": "headline.fetched",
                "schema_version": "v1",
                "symbol": symbol.upper(),
                "headline": h.get("headline", ""),
                "content": h.get("content", ""),
                "source_url": url,
                "source_name": h.get("source_name", ""),
                "published_at": h.get("published_at", ""),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }

            # Publish to durable stream for SentimentOrchestrator
            self._bus.publish("ingestion.news", event_payload)

            # Mark seen
            self._redis.set(dedup_key, "1", ex=TTL.NEWS_DEDUP)
            count += 1

        Logger.info("[%s] Ingested %d new headlines (fetched %d total)", symbol, count, len(headlines))

    # ── Market Price ────────────────────────────────────────────

    async def ingest_market_data(self, symbol: str) -> None:
        try:
            data = await self._price.fetch(symbol)
        except Exception as e:
            Logger.error("[%s] Failed to fetch market price: %s", symbol, e)
            return

        if not data:
            Logger.warning("[%s] No market price data", symbol)
            return

        # Cache price snapshot in Redis for API reads
        cache_key = RedisKeys.MARKET_PRICE.format(symbol=symbol.upper())
        self._redis.set(cache_key, json.dumps(data, default=str), ex=TTL.MARKET_PRICE)
        Logger.info("[%s] Cached market price: %.2f", symbol, data.get("last_price", 0))

    # ── Options ─────────────────────────────────────────────────

    async def ingest_options(self, symbol: str) -> None:
        try:
            data = await self._option.fetch(symbol)
        except Exception as e:
            Logger.error("[%s] Failed to fetch option chain: %s", symbol, e)
            return

        if not data:
            Logger.warning("[%s] No option chain data", symbol)
            return

        # Add fetched_at timestamp
        data["fetched_at"] = datetime.now(timezone.utc).isoformat()

        cache_key = RedisKeys.MARKET_OPTIONS.format(symbol=symbol.upper())
        self._redis.set(cache_key, json.dumps(data, default=str), ex=TTL.MARKET_OPTIONS)
        Logger.info("[%s] Cached option chain (%d expiries)", symbol, len(data.get("expiry_dates", [])))
