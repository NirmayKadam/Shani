"""
File Overview: At-least-once Redis Streams consumer loop built on DurableEventStream.

All Functions/Classes:
- run_durable_consumer: Read a stream through a consumer group, call the handler for each message,
  ACK on success, retry then dead-letter on failure. Data: Redis Stream -> handler(payload).

Guarantees: a message is ACKed only after its handler succeeds. If the process dies mid-message,
the entry stays in the group's Pending Entries List and is reclaimed (XAUTOCLAIM) by the next
consumer once it has been idle for min_idle_ms. Handlers must therefore tolerate redelivery.

Endpoints/APIs: None

Database Tables: Redis Streams
"""
import asyncio
import logging
import os
import socket
import time
from typing import Awaitable, Callable, Optional

from shared.infrastructure.event_bus.streams import DurableEventStream

logger = logging.getLogger(__name__)


async def run_durable_consumer(
    redis_client,
    *,
    stream: str,
    group: str,
    dlq_stream: str,
    handler: Callable[[dict], Awaitable[None]],
    max_retries: int = 3,
    batch_size: int = 5,
    block_ms: int = 5000,
    claim_every_seconds: float = 30.0,
    min_idle_ms: int = 60_000,
    stop_event: Optional[asyncio.Event] = None,
) -> None:
    bus = DurableEventStream(redis_client, max_retries=max_retries)
    # A new group starts at "$": the stream's existing history is not replayed on first deploy.
    await bus.ensure_group(stream, group, start_id="$")
    consumer = f"{socket.gethostname()}-{os.getpid()}"
    last_claim = 0.0
    logger.info("Consumer %s reading %s as group %s", consumer, stream, group)

    while stop_event is None or not stop_event.is_set():
        try:
            messages = []
            if time.monotonic() - last_claim >= claim_every_seconds:
                last_claim = time.monotonic()
                # Messages delivered to a consumer that crashed before ACKing
                messages += await bus.claim_stale(
                    stream=stream, group=group, consumer=consumer, min_idle_ms=min_idle_ms,
                )
            messages += await bus.read_group(
                group=group, consumer=consumer, streams=[stream], count=batch_size, block_ms=block_ms,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Error reading %s: %s", stream, exc)
            await asyncio.sleep(2)
            continue

        for message in messages:
            try:
                await handler(message.payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Handler failed for %s %s (retry %d): %s",
                             stream, message.message_id, message.retry_count, exc, exc_info=True)
                await bus.retry_or_dead_letter(
                    stream=stream, dlq_stream=dlq_stream, group=group, message=message, error=exc,
                )
            else:
                await bus.ack(stream, group, message.message_id)
