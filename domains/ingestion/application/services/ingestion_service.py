"""
File Overview: Application service orchestrating news, price, and options ingestion logic.
Follows hexagonal architecture — depends on port interfaces, not concrete adapters.

All Functions/Classes:
- ingestion_service: Core ingestion manager. Data: external fetchers -> Redis snapshots / event bus.
- ingest_news: Fetch and deduplicate headlines. Data: symbol -> ingestion.news durable stream.
- ingest_market_data: Fetch spot prices. Data: symbol -> MARKET_PRICE Redis cache.
- ingest_options: Fetch option chains. Data: symbol -> MARKET_OPTIONS Redis cache.

Endpoints/APIs: None (Orchestrated by Celery Tasks)

Database Tables: Redis (Deduplication, KV Cache, Streams)
"""
import hashlib
import json
import logging
from datetime import datetime, timezone

from shared.constants import RedisKeys, Streams, TTL, Channels
from domains.ingestion.ports.interface.outbound.i_news_source_port import INewsSourcePort
from domains.ingestion.ports.interface.outbound.i_option_chain_source_port import IOptionChainSourcePort
from domains.ingestion.ports.interface.outbound.i_market_price_source_port import IMarketPriceSourcePort
from domains.ingestion.ports.interface.outbound.i_event_publisher_port import IEventPublisherPort
from domains.ingestion.ports.interface.outbound.i_dedup_store_port import IDedupStorePort

logger = logging.getLogger(__name__)


class IngestionService:
    """Orchestrates news, price, and options ingestion.

    Uses async Redis.
    Depends on port interfaces — concrete adapters injected via constructor.
    """

    def __init__(
        self,
        news_fetcher: INewsSourcePort,
        price_fetcher: IMarketPriceSourcePort,
        option_fetcher: IOptionChainSourcePort,
        dedup_store: IDedupStorePort,
        event_bus: IEventPublisherPort,
        redis_client=None, # For caching until we have ICachePort
    ):
        self._news = news_fetcher
        self._price = price_fetcher
        self._option = option_fetcher
        self._dedup = dedup_store
        self._bus = event_bus
        self._redis = redis_client

    # ── News ────────────────────────────────────────────────────

    async def ingest_news(self, symbol: str) -> None:
        try:
            headlines = await self._news.fetch_articles(symbol)
        except Exception as e:
            logger.error("[%s] Failed to fetch news: %s", symbol, e)
            return

        if not headlines:
            logger.warning("[%s] No headlines fetched after query fallbacks", symbol)
            return

        count = 0
        for h in headlines:
            url = h.url
            # Deterministic hash — consistent across processes
            # Using 16 hex chars (64 bits) for low collision probability
            url_hash = hashlib.md5(url.encode()).hexdigest()[:16]
            
            if await self._dedup.is_seen(url_hash):
                continue

            # Build event payload matching HeadlineFetchedV1 contract
            event_payload = {
                "event_type": "headline.fetched",
                "schema_version": "v1",
                "symbol": symbol.upper(),
                "headline": h.headline,
                "content": h.body,
                "source_url": url,
                "source_name": h.source,
                "published_at": h.published_at,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }

            # Publish to durable stream for sentiment_orchestrator
            await self._bus.publish("ingestion.news", event_payload)

            # Mark seen
            await self._dedup.mark_seen(url_hash)
            count += 1

        logger.info("[%s] Ingested %d new headlines (fetched %d total)", symbol, count, len(headlines))

    # ── Market Price ────────────────────────────────────────────

    async def ingest_market_data(self, symbol: str) -> None:
        try:
            data = await self._price.fetch_price(symbol)
        except Exception as e:
            logger.error("[%s] Failed to fetch market price: %s", symbol, e)
            return

        if not data:
            logger.warning("[%s] No market price data", symbol)
            return

        # Cache price snapshot in Redis for API reads
        cache_key = RedisKeys.MARKET_PRICE.format(symbol=symbol.upper())
        await self._redis.set(cache_key, json.dumps(data, default=str), ex=TTL.MARKET_PRICE)
        logger.info("[%s] Cached market price: %.2f", symbol, data.get("last_price", 0))

        # Publish to Redis Pub/Sub for live real-time clients
        pub_channel = Channels.PRICE_UPDATED.format(symbol=symbol.upper())
        await self._redis.publish(pub_channel, json.dumps(data, default=str))

    # ── Options ─────────────────────────────────────────────────

    async def ingest_options(self, symbol: str) -> None:
        try:
            dtos = await self._option.fetch_option_chain(symbol)
        except Exception as e:
            logger.error("[%s] Failed to fetch option chain: %s", symbol, e)
            return

        if not dtos:
            logger.warning("[%s] No option chain data", symbol)
            return

        # Reconstruct OptionChainSummaryDTO dict format from RawTickDTO list
        spot_price = dtos[0].underlying_price
        chains = {}
        expiry_dates = set()
        
        for dto in dtos:
            if not dto.expiry: continue
            expiry_dates.add(dto.expiry)
            if dto.expiry not in chains:
                chains[dto.expiry] = []
            chains[dto.expiry].append({
                "strike": dto.strike,
                "type": dto.option_type,
                "last_price": dto.ltp,
                "oi": dto.oi,
                "volume": dto.volume,
                "iv": dto.iv,
                "expiry": dto.expiry
            })

        data = {
            "symbol": symbol.upper(),
            "spot_price": spot_price,
            "expiry_dates": sorted(list(expiry_dates)),
            "chains": chains,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "summary": {"total_strikes": len(set(d.strike for d in dtos))}
        }

        cache_key = RedisKeys.MARKET_OPTIONS.format(symbol=symbol.upper())
        await self._redis.set(cache_key, json.dumps(data, default=str), ex=TTL.MARKET_OPTIONS)
        logger.info("[%s] Cached option chain (%d expiries)", symbol, len(data.get("expiry_dates", [])))

        # Publish to Redis Pub/Sub for live real-time clients
        pub_channel = Channels.OPTIONS_UPDATED.format(symbol=symbol.upper())
        await self._redis.publish(pub_channel, json.dumps({"symbol": symbol.upper(), "status": "updated"}))
