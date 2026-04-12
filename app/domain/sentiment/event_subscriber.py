# app/domain/sentiment/event_subscriber.py — Real-time event listener
#
# Replaces Celery for the Sentiment domain. Listens directly to Redis Pub/Sub,
# scores headlines with FinBERT, persists to Postgres, computes multi-timeframe
# sentiment, and publishes aggregate events back to the bus.

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

from app.config import GetSettings
from app.shared.redis_client import GetRedisClient
from app.shared.database import GetDatabasePool
from app.shared.constants import Channels, RedisKeys, TTL
from app.shared.event_bus import EventBus
from app.domain.sentiment.finbert_engine import FinBertEngine
from app.domain.sentiment.analyzer import SentimentAnalyzer
from app.domain.sentiment.timeframes import TimeframeComputer

# Configure root logger for the script
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
Logger = logging.getLogger(" sentiment_subscriber")


async def handle_headline(channel: str, event: dict) -> None:
    """Invoked when 'headlines.fetched.*' event is received."""
    symbol = event.get("symbol", "")
    if not symbol:
        return

    analyzer = SentimentAnalyzer()
    scored = await analyzer.score_headlines([event])
    if not scored:
        return

    result = scored[0]
    redis = await GetRedisClient()
    db_pool = await GetDatabasePool()

    # 1. Store in Redis sorted set (latest 50)
    headlines_key = RedisKeys.NEWS_HEADLINES.format(symbol=symbol.upper())
    headline_json = json.dumps(result, default=str)
    try:
        ts_dt = datetime.fromisoformat(result.get("published_at", "").replace("Z", "+00:00"))
    except (ValueError, TypeError):
        ts_dt = datetime.now(timezone.utc)

    pipe = redis.pipeline()
    pipe.zadd(headlines_key, {headline_json: ts_dt.timestamp()})
    pipe.zremrangebyrank(headlines_key, 0, -51)
    pipe.expire(headlines_key, TTL.HEADLINES)
    # Cache latest individual score
    latest_key = RedisKeys.SENTIMENT_LATEST.format(symbol=symbol.upper())
    pipe.set(latest_key, headline_json, ex=TTL.SENTIMENT_LATEST)
    await pipe.execute()

    # Publish SentimentScored event
    await redis.publish(Channels.SENTIMENT_SCORED.format(symbol=symbol.upper()), headline_json)
    
    # 2. Write to PostgreSQL SentimentScores
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO SentimentScores 
            (Symbol, SentimentLabel, SentimentScore, Confidence, SourceType, SourceUrl, Headline, CreatedAt)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            symbol.upper(),
            result["sentiment_label"],
            result["sentiment_score"],
            result["confidence"],
            "NEWS",
            result.get("source_url", ""),
            result.get("headline", ""),
            ts_dt
        )

    Logger.info("[%s] Scored & Saved: %s → %s (%.3f)", symbol, result.get("headline", "")[:50], result["sentiment_label"], result["sentiment_score"])

    # 3. Recompute Aggregates and Publish
    await recompute_and_publish_aggregates(symbol.upper(), redis, db_pool)


async def handle_price_trigger(channel: str, event: dict) -> None:
    """Invoked when 'market.price_trigger.*' is received. Injects synthetic sentiment."""
    symbol = event.get("symbol", "")
    trigger_type = event.get("trigger_type", "")
    if not symbol or not trigger_type:
        return

    # Determine synthetic score based on trigger
    if trigger_type == "FLASH_DROP":
        label = "BEARISH"
        score = -0.90
    elif trigger_type == "SPIKE_UP":
        label = "BULLISH"
        score = 0.90
    else:
        # High volatility / Volume anomalies amplify neutral uncertainty or slight bias
        label = "NEUTRAL"
        score = 0.0

    db_pool = await GetDatabasePool()
    ts_dt = datetime.fromisoformat(event.get("triggered_at", "").replace("Z", "+00:00"))

    # Write synthetic trigger as a sentiment score directly to PG
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO SentimentScores 
            (Symbol, SentimentLabel, SentimentScore, Confidence, SourceType, Headline, CreatedAt)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            symbol.upper(),
            label,
            score,
            1.0,
            "MARKET",
            event.get("description", f"Price trigger: {trigger_type}"),
            ts_dt
        )

    Logger.warning("[%s] Injecting synthetic AI signal for trigger %s: %s (%.2f)", symbol, trigger_type, label, score)
    
    # Recompute aggregates so the synthethic sentiment affects the timelines immediately
    redis = await GetRedisClient()
    await recompute_and_publish_aggregates(symbol.upper(), redis, db_pool)


async def recompute_and_publish_aggregates(symbol: str, redis, db_pool) -> None:
    """Queries Postgres for the last 30 days of scores for a symbol and recomputes multi-timeframe sentiment."""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT SentimentLabel as sentiment_label, SentimentScore as sentiment_score, CreatedAt as published_at
            FROM SentimentScores 
            WHERE Symbol = $1 AND CreatedAt >= NOW() - INTERVAL '60 days'
            """,
            symbol
        )

    if not rows:
        return

    # Format for TimeframeComputer
    headline_list = []
    for r in rows:
        headline_list.append({
            "sentiment_label": r["sentiment_label"],
            "sentiment_score": float(r["sentiment_score"]),
            "published_at": r["published_at"].isoformat()
        })

    computer = TimeframeComputer()
    tf_data = computer.compute_all(headline_list)

    # Publish each aggregate
    for tf, agg in tf_data.items():
        agg_event = {
            "symbol": symbol,
            "timeframe": tf,
            **agg
        }
        # Publish event
        await redis.publish(Channels.AGGREGATE_UPDATED.format(symbol=symbol), json.dumps(agg_event, default=str))

        # Update cache for API reads
        cache_key = RedisKeys.SENTIMENT_AGG.format(symbol=symbol, tf=tf)
        await redis.set(cache_key, json.dumps(agg_event, default=str), ex=TTL.SENTIMENT_AGG)

    Logger.info("[%s] Recomputed multi-timeframe aggregates (scored items: %d)", symbol, len(headline_list))


async def main():
    Logger.info("Starting Sentiment Event Subscriber...")
    cfg = GetSettings()
    
    # Initialize DB & Redis
    redis = await GetRedisClient()
    await GetDatabasePool()

    # Pre-load FinBERT into memory
    FinBertEngine.get_instance(cache_path=cfg.ModelCacheDir)

    bus = EventBus(redis)
    await bus.subscribe(Channels.HEADLINE_FETCHED.format(symbol="*"), handle_headline)
    await bus.subscribe(Channels.PRICE_TRIGGER.format(symbol="*"), handle_price_trigger)

    try:
        await bus.listen() # Blocking call
    except KeyboardInterrupt:
        Logger.info("Subscriber interrupted.")
    finally:
        await bus.stop()


if __name__ == "__main__":
    asyncio.run(main())
