# app/domain/ingestion/tasks.py — Celery tasks for periodic data polling
#
# These tasks are triggered by Celery Beat and publish events
# to the event bus for other domains to consume.

import asyncio
import json
import logging
import os

Logger = logging.getLogger(__name__)

_WATCHLIST_RAW = os.getenv(
    "WATCHLIST_SYMBOLS", "NIFTY,BANKNIFTY,RELIANCE,INFY,HDFCBANK,TCS,ICICIBANK"
)
_WATCHLIST = [s.strip() for s in _WATCHLIST_RAW.split(",") if s.strip()]


def _get_or_create_loop():
    """Get the current event loop or create a new one for Celery workers."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


# ── Lazy import to avoid circular deps ─────────────────────────

def _get_celery_app():
    from app.celery_app import CeleryApp
    return CeleryApp


# ── News Polling Task ──────────────────────────────────────────

@_get_celery_app().task(name="ingestion.poll_news", queue="ingestion", bind=True)
def PollNewsTask(self):
    """Periodically fetch new headlines for all watchlist symbols."""
    try:
        loop = _get_or_create_loop()
        loop.run_until_complete(_poll_news_async())
    except Exception as exc:
        Logger.error(f"PollNewsTask failed: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60, max_retries=3)


async def _poll_news_async():
    from app.domain.ingestion.news_fetcher import NewsFetcher
    from app.shared.redis_client import GetRedisClient
    from app.shared.constants import Channels, RedisKeys, Streams, TTL
    from app.shared.event_bus.contracts import HeadlineFetchedEvent
    from app.shared.event_bus.streams import DurableEventStream
    from app.config import GetSettings

    cfg = GetSettings()
    fetcher = NewsFetcher(api_key=cfg.NewsApiKey)
    redis = await GetRedisClient()
    stream_bus = DurableEventStream(redis)

    try:
        for symbol in _WATCHLIST:
            headlines = await fetcher.fetch(symbol)

            for h in headlines:
                # Publish each headline as an event
                event = HeadlineFetchedEvent(
                    symbol=symbol.upper(),
                    headline=h["headline"],
                    content=h["content"],
                    source_url=h["source_url"],
                    source_name=h["source_name"],
                    published_at=h["published_at"],
                ).to_dict()
                await stream_bus.publish(Streams.HEADLINE_FETCHED, event)
                channel = Channels.HEADLINE_FETCHED.format(symbol=symbol.upper())
                await redis.publish(channel, json.dumps(event, default=str))

            Logger.info("[%s] Published %d headlines to event bus", symbol, len(headlines))
    finally:
        await fetcher.close()


from datetime import datetime, timezone

# ── Price Polling Task ─────────────────────────────────────────

@_get_celery_app().task(name="ingestion.poll_prices", queue="ingestion", bind=True)
def PollPricesTask(self):
    """Periodically fetch latest prices for all watchlist symbols."""
    try:
        loop = _get_or_create_loop()
        loop.run_until_complete(_poll_prices_async())
    except Exception as exc:
        Logger.error(f"PollPricesTask failed: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=15, max_retries=3)


async def _poll_prices_async():
    from app.domain.ingestion.market_data_fetcher import MarketPriceFetcher
    from app.domain.ingestion.price_triggers import PriceTriggerDetector
    from app.shared.redis_client import GetRedisClient
    from app.shared.database import GetDatabasePool
    from app.shared.constants import Channels, RedisKeys, Streams, TTL
    from app.shared.event_bus.contracts import PriceTriggerEvent, PriceUpdatedEvent
    from app.shared.event_bus.streams import DurableEventStream

    redis = await GetRedisClient()
    stream_bus = DurableEventStream(redis)
    db_pool = await GetDatabasePool()
    fetcher = MarketPriceFetcher()
    trigger_detector = PriceTriggerDetector(redis)
    now = datetime.now(timezone.utc)

    for symbol in _WATCHLIST:
        data = await fetcher.fetch(symbol)
        if not data:
            continue

        # Cache in Redis
        cache_key = RedisKeys.MARKET_PRICE.format(symbol=symbol.upper())
        await redis.set(cache_key, json.dumps(data, default=str), ex=TTL.MARKET_PRICE)

        # Write to Postgres TickData
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO TickData 
                (Timestamp, Symbol, Exchange, InstrumentType, LastPrice, Volume)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                now,
                symbol.upper(),
                "NSE",
                "EQ",
                data["last_price"],
                data.get("volume", 0)
            )

        # Publish price update event
        channel = Channels.PRICE_UPDATED.format(symbol=symbol.upper())
        price_event = PriceUpdatedEvent(
            symbol=symbol.upper(),
            last_price=float(data.get("last_price", 0.0)),
            open=float(data.get("open", 0.0)),
            high=float(data.get("high", 0.0)),
            low=float(data.get("low", 0.0)),
            volume=int(data.get("volume", 0)),
            previous_close=float(data.get("previous_close", 0.0)),
            change_percent=float(data.get("change_percent", 0.0)),
            market_status=str(data.get("market_status", "UNKNOWN")),
            last_updated=str(data.get("last_updated", now.isoformat())),
        )
        await redis.publish(channel, json.dumps(price_event.to_dict(), default=str))

        # Check for price triggers
        triggers = await trigger_detector.check(
            symbol,
            current_price=data["last_price"],
            current_volume=data.get("volume", 0),
        )
        for trigger in triggers:
            trigger_event = PriceTriggerEvent.from_dict(trigger)
            await stream_bus.publish(Streams.PRICE_TRIGGER, trigger_event.to_dict())
            trigger_channel = Channels.PRICE_TRIGGER.format(symbol=symbol.upper())
            await redis.publish(trigger_channel, json.dumps(trigger_event.to_dict(), default=str))

        Logger.debug("[%s] Price cached and DB write done: ₹%.2f", symbol, data["last_price"])


# ── Options Polling Task ───────────────────────────────────────

@_get_celery_app().task(name="ingestion.poll_options", queue="ingestion", bind=True)
def PollOptionsTask(self):
    """Periodically fetch option chains for all watchlist symbols."""
    try:
        loop = _get_or_create_loop()
        loop.run_until_complete(_poll_options_async())
    except Exception as exc:
        Logger.error(f"PollOptionsTask failed: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=30, max_retries=3)


async def _poll_options_async():
    import asyncio as aio
    from app.domain.ingestion.market_data_fetcher import OptionChainFetcher
    from app.shared.redis_client import GetRedisClient
    from app.shared.database import GetDatabasePool
    from app.shared.constants import Channels, RedisKeys, Streams, TTL
    from app.shared.event_bus.contracts import OptionsUpdatedEvent

    redis = await GetRedisClient()
    db_pool = await GetDatabasePool()
    fetcher = OptionChainFetcher()
    await fetcher.initialise()
    now = datetime.now(timezone.utc)

    try:
        for symbol in _WATCHLIST:
            data = await fetcher.fetch(symbol)
            if not data:
                continue

            # Cache in Redis
            cache_key = RedisKeys.MARKET_OPTIONS.format(symbol=symbol.upper())
            await redis.set(cache_key, json.dumps(data, default=str), ex=TTL.MARKET_OPTIONS)

            # Insert options into PostgreSQL TickData
            async with db_pool.acquire() as conn:
                inserts = []
                for expiry, chain_ticks in data["chains"].items():
                    for tick in chain_ticks:
                        expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
                        inserts.append((
                            now,
                            symbol.upper(),
                            "NSE",
                            tick["type"], # CE or PE
                            tick["last_price"],
                            tick["oi"],
                            tick["volume"],
                            expiry_date,
                            tick["strike"]
                        ))

                if inserts:
                    await conn.executemany(
                        """
                        INSERT INTO TickData 
                        (Timestamp, Symbol, Exchange, InstrumentType, LastPrice, OpenInterest, Volume, ExpiryDate, StrikePrice)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        """,
                        inserts
                    )

            # Publish options update event
            channel = Channels.OPTIONS_UPDATED.format(symbol=symbol.upper())
            # Send summary (not full chain — too large for pub/sub)
            summary_event = OptionsUpdatedEvent(
                symbol=symbol.upper(),
                spot_price=float(data.get("spot_price", 0.0)),
                expiry_dates=data.get("expiry_dates", []),
                summary=data.get("summary", {}),
            )
            await redis.publish(channel, json.dumps(summary_event.to_dict(), default=str))

            Logger.info("[%s] Options cached & %d ticks written to DB", symbol, sum(len(c) for c in data["chains"].values()))

            # Rate limit between symbols to avoid NSE blocking
            await aio.sleep(1.5)
    finally:
        await fetcher.close()


@_get_celery_app().task(name="ingestion.refresh_symbol", queue="ingestion", bind=True)
def RefreshSymbolTask(self, symbol: str):
    """On-demand refresh for a single symbol (API-triggered)."""
    try:
        loop = _get_or_create_loop()
        loop.run_until_complete(_refresh_symbol_async(symbol))
    except Exception as exc:
        Logger.error("RefreshSymbolTask failed for %s: %s", symbol, exc, exc_info=True)
        raise self.retry(exc=exc, countdown=20, max_retries=2)


async def _refresh_symbol_async(symbol: str):
    """Refreshes market + options + headlines for one symbol and publishes events."""
    symbol_upper = symbol.strip().upper()

    from app.config import GetSettings
    from app.domain.ingestion.market_data_fetcher import MarketPriceFetcher, OptionChainFetcher
    from app.domain.ingestion.news_fetcher import NewsFetcher
    from app.domain.ingestion.price_triggers import PriceTriggerDetector
    from app.shared.constants import Channels, RedisKeys, Streams, TTL
    from app.shared.database import GetDatabasePool
    from app.shared.event_bus.contracts import (
        HeadlineFetchedEvent,
        OptionsUpdatedEvent,
        PriceTriggerEvent,
        PriceUpdatedEvent,
    )
    from app.shared.redis_client import GetRedisClient
    from app.shared.event_bus.streams import DurableEventStream

    redis = await GetRedisClient()
    stream_bus = DurableEventStream(redis)
    db_pool = await GetDatabasePool()
    now = datetime.now(timezone.utc)

    # 1) Price snapshot
    try:
        price_fetcher = MarketPriceFetcher()
        price_data = await price_fetcher.fetch(symbol_upper)
        if price_data:
            await redis.set(
                RedisKeys.MARKET_PRICE.format(symbol=symbol_upper),
                json.dumps(price_data, default=str),
                ex=TTL.MARKET_PRICE,
            )

            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO TickData
                    (Timestamp, Symbol, Exchange, InstrumentType, LastPrice, Volume)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    now,
                    symbol_upper,
                    "NSE",
                    "EQ",
                    price_data.get("last_price"),
                    price_data.get("volume", 0),
                )

            price_event = PriceUpdatedEvent(
                symbol=symbol_upper,
                last_price=float(price_data.get("last_price", 0.0)),
                open=float(price_data.get("open", 0.0)),
                high=float(price_data.get("high", 0.0)),
                low=float(price_data.get("low", 0.0)),
                volume=int(price_data.get("volume", 0)),
                previous_close=float(price_data.get("previous_close", 0.0)),
                change_percent=float(price_data.get("change_percent", 0.0)),
                market_status=str(price_data.get("market_status", "UNKNOWN")),
                last_updated=str(price_data.get("last_updated", now.isoformat())),
            )
            await redis.publish(
                Channels.PRICE_UPDATED.format(symbol=symbol_upper),
                json.dumps(price_event.to_dict(), default=str),
            )

            trigger_detector = PriceTriggerDetector(redis)
            triggers = await trigger_detector.check(
                symbol_upper,
                current_price=price_data["last_price"],
                current_volume=price_data.get("volume", 0),
            )
            for trigger in triggers:
                trigger_event = PriceTriggerEvent.from_dict(trigger)
                await stream_bus.publish(Streams.PRICE_TRIGGER, trigger_event.to_dict())
                await redis.publish(
                    Channels.PRICE_TRIGGER.format(symbol=symbol_upper),
                    json.dumps(trigger_event.to_dict(), default=str),
                )
    except Exception as exc:
        Logger.warning("[%s] Refresh price step failed: %s", symbol_upper, exc)

    # 2) Options snapshot
    try:
        option_fetcher = OptionChainFetcher()
        await option_fetcher.initialise()
        try:
            options_data = await option_fetcher.fetch(symbol_upper)
        finally:
            await option_fetcher.close()

        if options_data:
            await redis.set(
                RedisKeys.MARKET_OPTIONS.format(symbol=symbol_upper),
                json.dumps(options_data, default=str),
                ex=TTL.MARKET_OPTIONS,
            )

            options_event = OptionsUpdatedEvent(
                symbol=symbol_upper,
                spot_price=float(options_data.get("spot_price", 0.0)),
                expiry_dates=options_data.get("expiry_dates", []),
                summary=options_data.get("summary", {}),
            )
            await redis.publish(
                Channels.OPTIONS_UPDATED.format(symbol=symbol_upper),
                json.dumps(options_event.to_dict(), default=str),
            )
    except Exception as exc:
        Logger.warning("[%s] Refresh options step failed: %s", symbol_upper, exc)

    # 3) Headlines -> publish events for NLP worker pipeline
    try:
        cfg = GetSettings()
        news_fetcher = NewsFetcher(api_key=cfg.NewsApiKey)
        try:
            headlines = await news_fetcher.fetch(symbol_upper, max_results=20)
        finally:
            await news_fetcher.close()

        for h in headlines:
            event = HeadlineFetchedEvent(
                symbol=symbol_upper,
                headline=h.get("headline", ""),
                content=h.get("content", ""),
                source_url=h.get("source_url", ""),
                source_name=h.get("source_name", ""),
                published_at=h.get("published_at", ""),
            ).to_dict()
            await stream_bus.publish(Streams.HEADLINE_FETCHED, event)
            await redis.publish(
                Channels.HEADLINE_FETCHED.format(symbol=symbol_upper),
                json.dumps(event, default=str),
            )
    except Exception as exc:
        Logger.warning("[%s] Refresh news step failed: %s", symbol_upper, exc)

    Logger.info("[%s] On-demand refresh command completed", symbol_upper)
