"""
File Overview: Application service orchestrating price and options ingestion logic.
Follows hexagonal architecture — depends on port interfaces, not concrete adapters.

All Functions/Classes:
- ingestion_service: Core ingestion manager. Data: external fetchers -> Redis snapshots / event bus.
- ingest_market_data: Fetch spot prices. Data: symbol -> MARKET_PRICE Redis cache.
- ingest_options: Fetch option chains. Data: symbol -> MARKET_OPTIONS Redis cache.

Endpoints/APIs: None (Orchestrated by Celery Tasks)

Database Tables: Redis (KV Cache, Streams)
"""
import json
import logging
from datetime import datetime, timezone

from shared.constants import RedisKeys, TTL, Channels
from domains.ingestion.ports.interface.outbound.i_option_chain_source_port import IOptionChainSourcePort
from domains.ingestion.ports.interface.outbound.i_market_price_source_port import IMarketPriceSourcePort
from domains.ingestion.ports.interface.outbound.i_event_publisher_port import IEventPublisherPort

logger = logging.getLogger(__name__)


def build_option_chain_snapshot(symbol: str, dtos: list) -> dict:
    """MARKET_OPTIONS read-model snapshot (chains grouped by expiry) built from RawTickDTOs."""
    chains: dict[str, list[dict]] = {}
    for dto in dtos:
        if not dto.expiry:
            continue
        chains.setdefault(dto.expiry, []).append({
            "strike": dto.strike,
            "type": dto.option_type,
            "last_price": dto.ltp,
            "oi": dto.oi,
            "volume": dto.volume,
            "iv": dto.iv,
            "bid": dto.bid,
            "bid_qty": dto.bid_qty,
            "ask": dto.ask,
            "ask_qty": dto.ask_qty,
            "expiry": dto.expiry,
        })

    return {
        "symbol": symbol.upper(),
        "spot_price": dtos[0].underlying_price if dtos else 0.0,
        "expiry_dates": sorted(chains),
        "chains": chains,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "summary": {"total_strikes": len({d.strike for d in dtos})},
    }


class IngestionService:
    """Orchestrates price and options ingestion.

    Uses async Redis.
    Depends on port interfaces — concrete adapters injected via constructor.
    """

    def __init__(
        self,
        price_fetcher: IMarketPriceSourcePort,
        option_fetcher: IOptionChainSourcePort,
        event_bus: IEventPublisherPort,
        redis_client=None, # For caching until we have ICachePort
    ):
        self._price = price_fetcher
        self._option = option_fetcher
        self._bus = event_bus
        self._redis = redis_client

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
        logger.debug("[%s] Cached market price: %.2f", symbol, data.get("last_price", 0))

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

        data = build_option_chain_snapshot(symbol, dtos)

        cache_key = RedisKeys.MARKET_OPTIONS.format(symbol=symbol.upper())
        await self._redis.set(cache_key, json.dumps(data, default=str), ex=TTL.MARKET_OPTIONS)
        logger.debug("[%s] Cached option chain (%d expiries)", symbol, len(data.get("expiry_dates", [])))

        # Publish to Redis Pub/Sub for live real-time clients
        pub_channel = Channels.OPTIONS_UPDATED.format(symbol=symbol.upper())
        await self._redis.publish(pub_channel, json.dumps({"symbol": symbol.upper(), "status": "updated"}))
