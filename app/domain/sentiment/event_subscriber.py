# app/domain/sentiment/event_subscriber.py — Real-time event listener
#
# Replaces Celery for the Sentiment domain. Listens directly to Redis Pub/Sub,
# scores headlines with FinBERT, persists to Postgres, computes multi-timeframe
# sentiment, and publishes aggregate events back to the bus.

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from app.config import GetSettings
from app.domain.sentiment.analyzer import SentimentAnalyzer
from app.domain.sentiment.finbert_engine import FinBertEngine
from app.domain.sentiment.timeframes import TimeframeComputer
from app.shared.constants import Channels, RedisKeys, TTL
from app.shared.database import GetDatabasePool
from app.shared.event_bus import EventBus
from app.shared.redis_client import GetRedisClient

# Configure root logger for the script
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
Logger = logging.getLogger(" sentiment_subscriber")


@dataclass(slots=True)
class SubscriberDependencies:
    analyzer: SentimentAnalyzer
    timeframe_computer: TimeframeComputer
    redis: object
    db_pool: object


async def handle_headline(channel: str, event: dict, deps: SubscriberDependencies) -> None:
    """Invoked when 'headlines.fetched.*' event is received."""
    symbol = event.get("symbol", "")
    if not symbol:
        return

    scored = await deps.analyzer.score_headlines([event])
    if not scored:
        return

    result = scored[0]

    # 1. Store in Redis sorted set (latest 50)
    headlines_key = RedisKeys.NEWS_HEADLINES.format(symbol=symbol.upper())
    headline_json = json.dumps(result, default=str)
    try:
        ts_dt = datetime.fromisoformat(result.get("published_at", "").replace("Z", "+00:00"))
    except (ValueError, TypeError):
        ts_dt = datetime.now(timezone.utc)

    pipe = deps.redis.pipeline()
    pipe.zadd(headlines_key, {headline_json: ts_dt.timestamp()})
    pipe.zremrangebyrank(headlines_key, 0, -51)
    pipe.expire(headlines_key, TTL.HEADLINES)
    # Cache latest individual score
    latest_key = RedisKeys.SENTIMENT_LATEST.format(symbol=symbol.upper())
    pipe.set(latest_key, headline_json, ex=TTL.SENTIMENT_LATEST)
    await pipe.execute()

    # Publish SentimentScored event
    await deps.redis.publish(Channels.SENTIMENT_SCORED.format(symbol=symbol.upper()), headline_json)

    # 2. Write to PostgreSQL SentimentScores
    async with deps.db_pool.acquire() as conn:
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
    await recompute_and_publish_aggregates(symbol.upper(), deps)


async def handle_price_trigger(channel: str, event: dict, deps: SubscriberDependencies) -> None:
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

    ts_str = event.get("triggered_at", "")
    try:
        ts_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        ts_dt = datetime.now(timezone.utc)

    # Write synthetic trigger as a sentiment score directly to PG
    async with deps.db_pool.acquire() as conn:
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

    # Recompute aggregates so the synthetic sentiment affects the timelines immediately
    await recompute_and_publish_aggregates(symbol.upper(), deps)


async def recompute_and_publish_aggregates(symbol: str, deps: SubscriberDependencies) -> None:
    """Queries Postgres for the last 30 days of scores for a symbol and recomputes multi-timeframe sentiment."""
    async with deps.db_pool.acquire() as conn:
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

    tf_data = deps.timeframe_computer.compute_all(headline_list)

    # Publish each aggregate
    for tf, agg in tf_data.items():
        agg_event = {
            "symbol": symbol,
            "timeframe": tf,
            **agg
        }
        # Publish event
        await deps.redis.publish(Channels.AGGREGATE_UPDATED.format(symbol=symbol), json.dumps(agg_event, default=str))

        # Update cache for API reads
        cache_key = RedisKeys.SENTIMENT_AGG.format(symbol=symbol, tf=tf)
        await deps.redis.set(cache_key, json.dumps(agg_event, default=str), ex=TTL.SENTIMENT_AGG)

    Logger.info("[%s] Recomputed multi-timeframe aggregates (scored items: %d)", symbol, len(headline_list))


async def main():
    Logger.info("Starting Sentiment Event Subscriber...")
    cfg = GetSettings()

    # Initialize long-lived shared dependencies once
    redis = await GetRedisClient()
    db_pool = await GetDatabasePool()
    finbert_engine = FinBertEngine.get_instance(cache_path=cfg.ModelCacheDir)
    analyzer = SentimentAnalyzer(finbert_engine)

    deps = SubscriberDependencies(
        analyzer=analyzer,
        timeframe_computer=TimeframeComputer(),
        redis=redis,
        db_pool=db_pool,
    )

    bus = EventBus(redis)
    await bus.subscribe(
        Channels.HEADLINE_FETCHED.format(symbol="*"),
        lambda channel, event: handle_headline(channel, event, deps),
    )
    await bus.subscribe(
        Channels.PRICE_TRIGGER.format(symbol="*"),
        lambda channel, event: handle_price_trigger(channel, event, deps),
    )

    try:
        await bus.listen()  # Blocking call
    except KeyboardInterrupt:
        Logger.info("Subscriber interrupted.")
    finally:
        finbert_engine.shutdown()
        await bus.stop()


if __name__ == "__main__":
    asyncio.run(main())
