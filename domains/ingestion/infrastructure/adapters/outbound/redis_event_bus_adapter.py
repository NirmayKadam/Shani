import json
import logging
import redis

from shared.constants import Streams

logger = logging.getLogger(__name__)

# Stream name mapping: event_type → Redis Stream
_EVENT_STREAM_MAP = {
    "ingestion.news": Streams.HEADLINE_FETCHED,
    "ingestion.mkt": Streams.PRICE_TRIGGER,  # not used for options; kept for compat
}

_RETRY_FIELD = "__retry_count"


class redis_event_bus_adapter:
    """Publishes domain events to Redis Streams (sync, for Celery workers)."""

    def __init__(self, redis_client: redis.Redis):
        self._redis = redis_client

    def publish(self, topic: str, payload: dict) -> None:
        stream = _EVENT_STREAM_MAP.get(topic)
        if not stream:
            logger.warning("No stream mapping for topic=%s, skipping publish", topic)
            return

        fields = {
            "payload": json.dumps(payload, default=str),
            _RETRY_FIELD: "0",
        }
        msg_id = self._redis.xadd(stream, fields, maxlen=10000, approximate=True)
        logger.info("Published to %s (msg_id=%s)", stream, msg_id)

    def publish_to_stream(self, stream: str, payload: dict) -> None:
        """Publish directly to a named stream."""
        fields = {
            "payload": json.dumps(payload, default=str),
            _RETRY_FIELD: "0",
        }
        msg_id = self._redis.xadd(stream, fields, maxlen=10000, approximate=True)
        logger.info("Published to %s (msg_id=%s)", stream, msg_id)
