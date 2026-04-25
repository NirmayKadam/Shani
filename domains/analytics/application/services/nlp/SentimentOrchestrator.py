# app/domain/sentiment/event_subscriber.py — Real-time event listener
#
# Replaces Celery for the Sentiment domain. Listens directly to Redis Pub/Sub,
# scores headlines with FinBERT, persists to Postgres, computes multi-timeframe
# sentiment, and publishes aggregate events back to the bus.

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from app.config import GetSettings
from domains.analytics.application.services.ml_forecasting.CNNPredictor import CNNPredictor
from domains.analytics.application.services.nlp.analyzer import SentimentAnalyzer
from domains.analytics.application.services.nlp.finbert_engine import FinBertEngine
from domains.analytics.application.services.nlp.timeframes import TimeframeComputer
from shared.constants import Channels, RedisKeys, StreamGroups, Streams, TTL
from shared.infrastructure.database import GetDatabasePool
from shared.infrastructure.event_bus.contracts import AggregateUpdatedEvent, PriceTriggerEvent, SentimentScoredEvent
from shared.infrastructure.event_bus.streams import DurableEventStream, StreamMessage
from shared.infrastructure.redis_client import GetRedisClient

# Configure root logger for the script
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
Logger = logging.getLogger(" sentiment_subscriber")
_CONSUMER_NAME = os.getenv("SENTIMENT_CONSUMER_NAME", "sentiment-worker-1")
_RETRY_IDLE_MS = int(os.getenv("SENTIMENT_RETRY_IDLE_MS", "30000"))


@dataclass(slots=True)
class SubscriberDependencies:
    analyzer: SentimentAnalyzer
    timeframe_computer: TimeframeComputer
    inference_engine: CNNPredictor | None
    redis: object
    db_pool: object
    stream_bus: DurableEventStream


async def handle_headline(channel: str, event: dict, deps: SubscriberDependencies) -> None:
    """Invoked when 'headlines.fetched.*' event is received."""
    symbol = str(event.get("symbol", "")).upper()
    headline = event.get("headline", "")
    if not symbol or not headline:
        return

    # 0. Deduplication check (avoid re-scoring identical headlines for the same symbol)
    headline_hash = hashlib.md5(headline.encode("utf-8")).hexdigest()
    dedup_key = f"seen:headline:{symbol}:{headline_hash}"
    if await deps.redis.exists(dedup_key):
        Logger.info("[%s] Skipping already seen headline: %s", symbol, headline[:50])
        return

    scored = await deps.analyzer.score_headlines([event])
    if not scored:
        return

    result = scored[0]
    scored_event = SentimentScoredEvent(
        symbol=symbol,
        headline=result.get("headline", ""),
        content=result.get("content", ""),
        source_url=result.get("source_url", ""),
        source_name=result.get("source_name", ""),
        published_at=result.get("published_at", ""),
        sentiment_label=result["sentiment_label"],
        sentiment_score=float(result["sentiment_score"]),
        confidence=float(result["confidence"]),
    )

    # 1. Store in Redis sorted set (latest 50)
    headlines_key = RedisKeys.NEWS_HEADLINES.format(symbol=symbol)

    # Strip scored_at to allow ZADD to deduplicate if re-scored later
    payload = scored_event.to_dict()
    payload.pop("scored_at", None)
    headline_json = json.dumps(payload, default=str, sort_keys=True)

    try:
        ts_dt = datetime.fromisoformat(result.get("published_at", "").replace("Z", "+00:00"))
    except (ValueError, TypeError):
        ts_dt = datetime.now(timezone.utc)

    pipe = deps.redis.pipeline()
    pipe.zadd(headlines_key, {headline_json: ts_dt.timestamp()})
    pipe.zremrangebyrank(headlines_key, 0, -51)
    pipe.expire(headlines_key, TTL.HEADLINES)
    # Cache latest individual score
    latest_key = RedisKeys.SENTIMENT_LATEST.format(symbol=symbol)
    pipe.set(latest_key, headline_json, ex=TTL.SENTIMENT_LATEST)
    # Mark as seen for 1 hour to prevent rapid duplicates
    pipe.set(dedup_key, "1", ex=3600)
    await pipe.execute()

    # Publish SentimentScored event (durable stream + ephemeral pub/sub mirror for websockets)
    # We still publish the event with scored_at to the bus for downstream consumers
    await deps.stream_bus.publish(Streams.SENTIMENT_SCORED, scored_event.to_dict())
    await deps.redis.publish(Channels.SENTIMENT_SCORED.format(symbol=symbol), headline_json)

    # 2. Write to PostgreSQL SentimentScores with existence check
    async with deps.db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO SentimentScores
            (Symbol, SentimentLabel, SentimentScore, Confidence, SourceType, SourceUrl, Headline, CreatedAt)
            SELECT $1::VARCHAR(20), $2::VARCHAR(10), $3, $4, $5::VARCHAR(10), $6, $7, $8
            WHERE NOT EXISTS (
                SELECT 1 FROM SentimentScores 
                WHERE Symbol = $1::VARCHAR(20) AND Headline = $7 AND CreatedAt = $8
            )
            """,
            symbol,
            scored_event.sentiment_label,
            scored_event.sentiment_score,
            scored_event.confidence,
            "NEWS",
            scored_event.source_url,
            scored_event.headline,
            ts_dt
        )

    Logger.info("[%s] Scored & Saved: %s → %s (%.3f)", symbol, scored_event.headline[:50], scored_event.sentiment_label, scored_event.sentiment_score)

    # 3. Recompute Aggregates and Publish
    tf_data = await recompute_and_publish_aggregates(symbol.upper(), deps)
    await compute_and_cache_ml_prediction(
        symbol=symbol.upper(),
        deps=deps,
        tf_data=tf_data,
    )


async def handle_price_trigger(channel: str, event: dict, deps: SubscriberDependencies) -> None:
    """Invoked when 'market.price_trigger.*' is received. Injects synthetic sentiment."""
    trigger_event = PriceTriggerEvent.from_dict(event)
    symbol = trigger_event.symbol
    trigger_type = trigger_event.trigger_type
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

    ts_str = trigger_event.triggered_at
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
            trigger_event.description or f"Price trigger: {trigger_type}",
            ts_dt
        )

    Logger.warning("[%s] Injecting synthetic AI signal for trigger %s: %s (%.2f)", symbol, trigger_type, label, score)

    # Recompute aggregates so the synthetic sentiment affects the timelines immediately
    tf_data = await recompute_and_publish_aggregates(symbol.upper(), deps)
    await compute_and_cache_ml_prediction(
        symbol=symbol.upper(),
        deps=deps,
        tf_data=tf_data,
    )


async def recompute_and_publish_aggregates(symbol: str, deps: SubscriberDependencies) -> dict[str, dict]:
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
        return {}

    # Format for TimeframeComputer
    headline_list = []
    for r in rows:
        headline_list.append({
            "sentiment_label": r["sentiment_label"],
            "sentiment_score": float(r["sentiment_score"]),
            "published_at": r["published_at"].isoformat()
        })

    # CPU-bound window filtering and aggregation should not block the event loop.
    tf_data = await asyncio.to_thread(deps.timeframe_computer.compute_all, headline_list)

    # Publish each aggregate
    for tf, agg in tf_data.items():
        agg_event = AggregateUpdatedEvent(
            symbol=symbol,
            timeframe=tf,
            label=agg.get("label", "NEUTRAL"),
            avg_score=float(agg.get("avg_score", 0.0)),
            bullish_pct=float(agg.get("bullish_pct", 0.0)),
            bearish_pct=float(agg.get("bearish_pct", 0.0)),
            neutral_pct=float(agg.get("neutral_pct", 0.0)),
            count=int(agg.get("count", 0)),
            trend=agg.get("trend", "STABLE"),
        ).to_dict()
        # Durable publish; downstream read-model updater owns persistence + websocket fan-out.
        await deps.stream_bus.publish(Streams.AGGREGATE_UPDATED, agg_event)

    Logger.info("[%s] Recomputed multi-timeframe aggregates (scored items: %d)", symbol, len(headline_list))
    return tf_data


async def compute_and_cache_ml_prediction(
    *,
    symbol: str,
    deps: SubscriberDependencies,
    tf_data: dict[str, dict],
) -> None:
    """Compute MTF-CNN-LSTM-VOL prediction out-of-band and cache it for API reads."""
    if deps.inference_engine is None or deps.inference_engine.model is None:
        return

    prediction = await asyncio.to_thread(
        deps.inference_engine.predict,
        symbol,
    )
    if not prediction or "error" in prediction:
        return

    payload = {
        **prediction,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    await deps.redis.set(
        RedisKeys.ML_PREDICTION.format(symbol=symbol),
        json.dumps(payload),
        ex=TTL.ML_PREDICTION,
    )
    Logger.info("[%s] Cached MTF-CNN-LSTM-VOL prediction", symbol)


async def main():
    Logger.info("Starting Sentiment Event Subscriber...")
    cfg = GetSettings()

    # Initialize long-lived shared dependencies once
    redis = await GetRedisClient()
    db_pool = await GetDatabasePool()
    finbert_engine = FinBertEngine.get_instance(cache_path=cfg.ModelCacheDir)
    analyzer = SentimentAnalyzer(finbert_engine)
    try:
        inference_engine = CNNPredictor()
    except Exception as e:
        Logger.warning("CNN model not available, predictions disabled: %s", e)
        inference_engine = None

    deps = SubscriberDependencies(
        analyzer=analyzer,
        timeframe_computer=TimeframeComputer(),
        inference_engine=inference_engine,
        redis=redis,
        db_pool=db_pool,
        stream_bus=DurableEventStream(redis),
    )
    await deps.stream_bus.ensure_group(Streams.HEADLINE_FETCHED, StreamGroups.INGESTION_TO_NLP)
    await deps.stream_bus.ensure_group(Streams.PRICE_TRIGGER, StreamGroups.INGESTION_TO_NLP)

    try:
        await _consume_ingestion_streams(deps)
    except KeyboardInterrupt:
        Logger.info("Subscriber interrupted.")
    finally:
        finbert_engine.shutdown()


async def _consume_ingestion_streams(deps: SubscriberDependencies) -> None:
    while True:
        messages = await deps.stream_bus.read_group(
            group=StreamGroups.INGESTION_TO_NLP,
            consumer=_CONSUMER_NAME,
            streams=[Streams.HEADLINE_FETCHED, Streams.PRICE_TRIGGER],
            count=20,
            block_ms=3000,
        )

        if not messages:
            stale_headlines = await deps.stream_bus.claim_stale(
                stream=Streams.HEADLINE_FETCHED,
                group=StreamGroups.INGESTION_TO_NLP,
                consumer=_CONSUMER_NAME,
                min_idle_ms=_RETRY_IDLE_MS,
                count=10,
            )
            stale_triggers = await deps.stream_bus.claim_stale(
                stream=Streams.PRICE_TRIGGER,
                group=StreamGroups.INGESTION_TO_NLP,
                consumer=_CONSUMER_NAME,
                min_idle_ms=_RETRY_IDLE_MS,
                count=10,
            )
            messages = stale_headlines + stale_triggers

        for message in messages:
            await _process_stream_message(deps, message)


async def _process_stream_message(deps: SubscriberDependencies, message: StreamMessage) -> None:
    try:
        if message.stream == Streams.HEADLINE_FETCHED:
            symbol = str(message.payload.get("symbol", "")).upper()
            await handle_headline(
                Channels.HEADLINE_FETCHED.format(symbol=symbol),
                message.payload,
                deps,
            )
        elif message.stream == Streams.PRICE_TRIGGER:
            symbol = str(message.payload.get("symbol", "")).upper()
            await handle_price_trigger(
                Channels.PRICE_TRIGGER.format(symbol=symbol),
                message.payload,
                deps,
            )
        else:
            Logger.warning("Unknown stream=%s message_id=%s", message.stream, message.message_id)

        await deps.stream_bus.ack(message.stream, StreamGroups.INGESTION_TO_NLP, message.message_id)
    except Exception as exc:
        await deps.stream_bus.retry_or_dead_letter(
            stream=message.stream,
            dlq_stream=Streams.INGESTION_TO_NLP_DLQ,
            group=StreamGroups.INGESTION_TO_NLP,
            message=message,
            error=exc,
        )


if __name__ == "__main__":
    asyncio.run(main())
