"""
File Overview: Async worker listening for on-demand refresh requests to trigger background ingestion.

All Functions/Classes:
- main: Infinite listener loop. Take events from ANALYSIS_REFRESH_REQUESTED stream and send to _handle_refresh.
- _handle_refresh: Refresh logic with cooldowns. Take refresh event and send Celery tasks for news/price/options/ML.

Endpoints/APIs: None (Background process)

Database Tables: Redis (Streams, Cooldown KV)
"""

import asyncio
import logging
import os

from shared.constants import StreamGroups, Streams
from shared.infrastructure.event_bus.streams import DurableEventStream, StreamMessage
from shared.infrastructure.redis_client import get_redis_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ingestion_orchestrator")

_CONSUMER_NAME = os.getenv("INGESTION_ORCH_CONSUMER_NAME", "ingestion-orch-1")
_GROUP = "cg:refresh_to_ingestion"
_COOLDOWN_SECONDS = int(os.getenv("INGESTION_REFRESH_COOLDOWN", "60"))

# Track last refresh per symbol to avoid hammering
_last_refresh: dict[str, float] = {}


async def main() -> None:
    logger.info("Starting Ingestion Orchestrator (refresh request consumer)...")
    redis = await get_redis_client()
    stream_bus = DurableEventStream(redis)

    await stream_bus.ensure_group(Streams.ANALYSIS_REFRESH_REQUESTED, _GROUP)

    while True:
        messages = await stream_bus.read_group(
            group=_GROUP,
            consumer=_CONSUMER_NAME,
            streams=[Streams.ANALYSIS_REFRESH_REQUESTED],
            count=20,
            block_ms=5000,
        )

        for message in messages:
            await _handle_refresh(stream_bus, message)


async def _handle_refresh(stream_bus: DurableEventStream, message: StreamMessage) -> None:
    try:
        symbol = str(message.payload.get("symbol", "")).upper()
        if not symbol:
            logger.warning("Refresh request missing symbol, skipping")
            await stream_bus.ack(Streams.ANALYSIS_REFRESH_REQUESTED, _GROUP, message.message_id)
            return

        # Cooldown check
        import time
        now = time.time()
        last = _last_refresh.get(symbol, 0)
        if now - last < _COOLDOWN_SECONDS:
            logger.info("[%s] Refresh cooldown active, skipping (last %.0fs ago)", symbol, now - last)
            await stream_bus.ack(Streams.ANALYSIS_REFRESH_REQUESTED, _GROUP, message.message_id)
            return

        _last_refresh[symbol] = now

        # Dispatch Celery tasks
        from domains.ingestion.application.tasks.ingestion_tasks import poll_news, poll_prices, poll_options
        from domains.analytics.application.tasks.ml_tasks import run_stock_prediction
        
        poll_news.delay(symbol)
        poll_prices.delay(symbol)
        poll_options.delay(symbol)
        run_stock_prediction.delay(symbol)

        logger.info("[%s] Dispatched ingestion + prediction tasks", symbol)
        await stream_bus.ack(Streams.ANALYSIS_REFRESH_REQUESTED, _GROUP, message.message_id)

    except Exception as exc:
        logger.error("Failed to handle refresh request: %s", exc, exc_info=True)
        await stream_bus.retry_or_dead_letter(
            stream=Streams.ANALYSIS_REFRESH_REQUESTED,
            dlq_stream=Streams.INGESTION_TO_NLP_DLQ,
            group=_GROUP,
            message=message,
            error=exc,
        )


if __name__ == "__main__":
    asyncio.run(main())
