"""
File Overview: Event-driven worker managing the end-to-end sentiment lifecycle: scoring, synthetic signal injection, and multi-timeframe aggregation.

All Functions/Classes:
- SubscriberDependencies (dataclass): Container for shared state and services.
- handle_headline: Handler for news ingestion events. Data: Headlines.fetched -> Scored/Persisted results.
- handle_price_trigger: Injects synthetic sentiment based on price volatility. Data: PriceTrigger -> Persisted synthetic signal.
- recompute_and_publish_aggregates: Rebuilds multi-timeframe stats from history. Data: Postgres history -> AggregateUpdated events.
- main: Application entry point for the worker loop. Data: Redis Streams -> Service Handlers.

Endpoints/APIs:
- None.

Database Tables:
- SentimentScores (Postgres), Redis (Streams, KV Cache, Pub/Sub).
"""
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

from app.config import get_settings
from domains.analytics.application.ports.interface.outbound.i_sentiment_store_port import ISentimentStorePort
from domains.analytics.application.ports.interface.outbound.i_event_publisher_port import IEventPublisherPort
from domains.analytics.application.ports.interface.outbound.i_cache_port import ICachePort
from domains.analytics.application.services.nlp.fin_bert_scorer_service import FinBertScorerService
from domains.analytics.application.services.ml_forecasting.daily_predictor_service import DailyPredictorService
from domains.analytics.application.services.nlp.signal_composer_service import SignalComposerService
from domains.analytics.domain.entities.sentiment_score_entity import SentimentScoreEntity
from domains.analytics.infrastructure.adapters.outbound.timescale_adapter import TimescaleAdapter
from domains.analytics.infrastructure.adapters.outbound.redis_adapter import RedisAdapter
from domains.analytics.application.services.nlp.timeframes_service import TimeframeComputerService
from shared.infrastructure.event_bus.contracts import PriceTriggerEvent
from shared.constants import RedisKeys, TTL, Streams, StreamGroups

logger = logging.getLogger(__name__)

_CONSUMER_NAME = "sentiment_orchestrator"

@dataclass(slots=True)
class SubscriberDependencies:
    scorer: FinBertScorerService
    timeframe_computer: TimeframeComputerService
    predictor: DailyPredictorService
    composer: SignalComposerService
    cache: ICachePort
    store: ISentimentStorePort
    publisher: IEventPublisherPort


async def handle_headline(channel: str, event: dict, deps: SubscriberDependencies) -> None:
    """Invoked when 'headlines.fetched.*' event is received."""
    symbol = str(event.get("symbol", "")).upper()
    headline = event.get("headline", "")
    content = event.get("content", "")
    if not symbol or not headline:
        return

    # 0. Deduplication check
    headline_hash = hashlib.md5(headline.encode("utf-8")).hexdigest()
    dedup_key = f"seen:headline:{symbol}:{headline_hash}"
    if await deps.cache.get(dedup_key):
        logger.info("[%s] Skipping already seen headline: %s", symbol, headline[:50])
        return

    # 1. Score headline
    scored = await deps.scorer.score_headlines([f"{headline} {content}"[:512]])
    if not scored:
        return

    result = scored[0]
    score_entity = SentimentScoreEntity(
        symbol=symbol,
        label=result["label"],
        score=result["score"],
        confidence=result["confidence"]
    )

    # 2. Persist to Postgres via Port
    await deps.store.save_score(score_entity)

    # 3. Cache latest & mark seen
    payload = {
        **event,
        "sentiment_label": score_entity.label,
        "sentiment_score": score_entity.score,
        "confidence": score_entity.confidence,
        "scored_at": datetime.now(timezone.utc).isoformat()
    }
    headline_json = json.dumps(payload, default=str)
    
    latest_key = RedisKeys.SENTIMENT_LATEST.format(symbol=symbol)
    await deps.cache.set(latest_key, headline_json, TTL.SENTIMENT_LATEST)
    await deps.cache.set(dedup_key, "1", TTL.NEWS_DEDUP)

    # Cache scored headline in the zset for read model
    published_str = event.get("published_at", "")
    try:
        dt = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
        score = dt.timestamp()
    except Exception:
        score = datetime.now(timezone.utc).timestamp()

    headlines_key = RedisKeys.NEWS_HEADLINES.format(symbol=symbol)
    await deps.cache.zadd(headlines_key, score, headline_json)
    await deps.cache.zremrangebyrank(headlines_key, 0, -21)

    # 4. Publish events
    await deps.publisher.publish(Streams.SENTIMENT_SCORED, payload)
    
    # 5. Recompute Aggregates & Fusion
    await _recompute_all(symbol, deps)


async def handle_price_trigger(channel: str, event: dict, deps: SubscriberDependencies) -> None:
    """Injects synthetic sentiment based on price volatility."""
    trigger_event = PriceTriggerEvent.from_dict(event)
    symbol = trigger_event.symbol.upper()
    trigger_type = trigger_event.trigger_type

    # Determine synthetic score
    label, score = "NEUTRAL", 0.0
    if trigger_type == "FLASH_DROP":
        label, score = "BEARISH", -0.90
    elif trigger_type == "SPIKE_UP":
        label, score = "BULLISH", 0.90

    score_entity = SentimentScoreEntity(
        symbol=symbol,
        label=label,
        score=score,
        confidence=1.0
    )
    
    await deps.store.save_score(score_entity)
    logger.warning("[%s] Injected synthetic signal: %s (%.2f)", symbol, label, score)

    await _recompute_all(symbol, deps)


async def _recompute_all(symbol: str, deps: SubscriberDependencies) -> None:
    """Orchestrates timeframe recomputation, ML prediction, and signal fusion."""
    # 1. Multi-timeframe aggregation
    tf_data = await recompute_and_publish_aggregates(symbol, deps)
    if not tf_data:
        return

    # 2. ML Prediction
    prediction = await deps.predictor.generate_prediction(symbol)
    
    # Cache prediction for API
    pred_key = RedisKeys.ML_PREDICTION.format(symbol=symbol)
    await deps.cache.set(pred_key, json.dumps(prediction), TTL.ML_PREDICTION)

    # 3. Signal Fusion
    composite_signal = deps.composer.compose_signal(symbol, tf_data, prediction)
    
    # Cache composite signal for API read model
    signal_key = RedisKeys.SENTIMENT_SIGNAL.format(symbol=symbol)
    await deps.cache.set(signal_key, json.dumps(composite_signal), TTL.SENTIMENT_SIGNAL)
    
    # Publish final signal
    await deps.publisher.publish(Streams.ANALYSIS_COMPLETED, composite_signal)
    logger.info("[%s] Analysis cycle complete: %s (Strength: %.2f)", 
                symbol, composite_signal["composite_label"], composite_signal["strength"])


async def recompute_and_publish_aggregates(symbol: str, deps: SubscriberDependencies) -> dict:
    """Queries history and computes TF stats."""
    scores = await deps.store.get_last_n(symbol, 1000)
    if not scores:
        return {}

    headline_list = [
        {
            "sentiment_label": s.label,
            "sentiment_score": s.score,
            "published_at": datetime.now(timezone.utc).isoformat() # Approx for older scores if missing
        }
        for s in scores
    ]

    tf_data = await asyncio.to_thread(deps.timeframe_computer.compute_all, headline_list)
    
    # Publish each aggregate for read-model updates
    for tf, agg in tf_data.items():
        await deps.publisher.publish(Streams.AGGREGATE_UPDATED, {
            "symbol": symbol,
            "timeframe": tf,
            **agg
        })
    
    return tf_data


async def main():
    logger.info("Starting Sentiment Event Subscriber...")
    redis_adapter = RedisAdapter()
    
    deps = SubscriberDependencies(
        scorer=FinBertScorerService(),
        timeframe_computer=TimeframeComputerService(),
        predictor=DailyPredictorService(),
        composer=SignalComposerService(),
        cache=redis_adapter,
        store=TimescaleAdapter(),
        publisher=redis_adapter
    )

    stream_bus = await redis_adapter._get_stream_bus()
    await stream_bus.ensure_group(Streams.HEADLINE_FETCHED, StreamGroups.INGESTION_TO_NLP)
    await stream_bus.ensure_group(Streams.PRICE_TRIGGER, StreamGroups.INGESTION_TO_NLP)
    
    await stream_bus.ensure_group(Streams.ANALYSIS_REFRESH_REQUESTED, StreamGroups.REFRESH_TO_SENTIMENT)

    while True:
        messages = await stream_bus.read_group(
            group=StreamGroups.INGESTION_TO_NLP,
            consumer=_CONSUMER_NAME,
            streams=[Streams.HEADLINE_FETCHED, Streams.PRICE_TRIGGER],
            count=20,
            block_ms=3000,
        )

        refresh_messages = await stream_bus.read_group(
            group=StreamGroups.REFRESH_TO_SENTIMENT,
            consumer=_CONSUMER_NAME,
            streams=[Streams.ANALYSIS_REFRESH_REQUESTED],
            count=10,
            block_ms=1000,
        )

        all_msgs = (messages or []) + (refresh_messages or [])
        for msg in all_msgs:
            group = StreamGroups.REFRESH_TO_SENTIMENT if msg.stream == Streams.ANALYSIS_REFRESH_REQUESTED else StreamGroups.INGESTION_TO_NLP
            dlq_stream = Streams.REFRESH_REQUEST_DLQ if group == StreamGroups.REFRESH_TO_SENTIMENT else Streams.INGESTION_TO_NLP_DLQ
            try:
                if msg.stream == Streams.HEADLINE_FETCHED:
                    await handle_headline("", msg.payload, deps)
                elif msg.stream == Streams.PRICE_TRIGGER:
                    await handle_price_trigger("", msg.payload, deps)
                elif msg.stream == Streams.ANALYSIS_REFRESH_REQUESTED:
                    symbol = str(msg.payload.get("symbol", "")).upper()
                    if symbol:
                        await _recompute_all(symbol, deps)
                
                await stream_bus.ack(msg.stream, group, msg.message_id)
            except Exception as exc:
                logger.error("Processing failed for %s: %s", msg.stream, exc)
                try:
                    await stream_bus.retry_or_dead_letter(
                        stream=msg.stream,
                        dlq_stream=dlq_stream,
                        group=group,
                        message=msg,
                        error=exc,
                    )
                except Exception as dlq_exc:
                    logger.error("Failed to route message %s to DLQ: %s", msg.message_id, dlq_exc)


if __name__ == "__main__":
    try:
        import uvloop
        uvloop.install()
    except ImportError:
        pass
    asyncio.run(main())
