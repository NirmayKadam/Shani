import asyncio
import json
import logging
import os

from shared.constants import Channels, RedisKeys, StreamGroups, Streams, TTL
from shared.infrastructure.event_bus.contracts import AggregateUpdatedEvent
from shared.infrastructure.event_bus.streams import DurableEventStream, StreamMessage
from shared.infrastructure.redis_client import get_redis_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("read_model_updater")
_CONSUMER_NAME = os.getenv("READ_MODEL_CONSUMER_NAME", "read-model-updater-1")
_RETRY_IDLE_MS = int(os.getenv("READ_MODEL_RETRY_IDLE_MS", "30000"))


async def main() -> None:
    logger.info("Starting NLP -> API read-model updater...")
    redis = await get_redis_client()
    stream_bus = DurableEventStream(redis)

    await stream_bus.ensure_group(Streams.AGGREGATE_UPDATED, StreamGroups.NLP_TO_API)

    while True:
        messages = await stream_bus.read_group(
            group=StreamGroups.NLP_TO_API,
            consumer=_CONSUMER_NAME,
            streams=[Streams.AGGREGATE_UPDATED],
            count=50,
            block_ms=3000,
        )

        if not messages:
            messages = await stream_bus.claim_stale(
                stream=Streams.AGGREGATE_UPDATED,
                group=StreamGroups.NLP_TO_API,
                consumer=_CONSUMER_NAME,
                min_idle_ms=_RETRY_IDLE_MS,
                count=20,
            )

        for message in messages:
            await _process_message(redis, stream_bus, message)


async def _process_message(redis, stream_bus: DurableEventStream, message: StreamMessage) -> None:
    try:
        event = AggregateUpdatedEvent.from_dict(message.payload)
        payload = event.to_dict()

        symbol = event.symbol.upper()
        timeframe = event.timeframe
        body = json.dumps(payload, default=str)

        cache_key = RedisKeys.SENTIMENT_AGG.format(symbol=symbol, tf=timeframe)
        await redis.set(cache_key, body, ex=TTL.SENTIMENT_AGG)

        # Pub/Sub remains UX-only for websocket fan-out.
        await redis.publish(Channels.AGGREGATE_UPDATED.format(symbol=symbol), body)

        await stream_bus.ack(message.stream, StreamGroups.NLP_TO_API, message.message_id)
        logger.info("[%s] Updated aggregate read model (%s)", symbol, timeframe)
    except Exception as exc:
        await stream_bus.retry_or_dead_letter(
            stream=message.stream,
            dlq_stream=Streams.NLP_TO_API_DLQ,
            group=StreamGroups.NLP_TO_API,
            message=message,
            error=exc,
        )


if __name__ == "__main__":
    asyncio.run(main())
