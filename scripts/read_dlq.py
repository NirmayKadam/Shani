"""
File Overview: Print the newest entries of a Redis Streams dead-letter queue.

Usage:
    python scripts/read_dlq.py [STREAM] [--count N] [--redis-url URL]

STREAM defaults to the refresh-request DLQ (Streams.REFRESH_REQUEST_DLQ).
"""
import argparse
import json
import os
import sys
from pathlib import Path

import redis

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared.constants import Streams  # noqa: E402


def _decode(value):
    return value.decode() if isinstance(value, bytes) else value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stream", nargs="?", default=Streams.REFRESH_REQUEST_DLQ)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--redis-url", default=os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"))
    args = parser.parse_args()

    client = redis.from_url(args.redis_url)
    entries = client.xrevrange(args.stream, count=args.count)
    if not entries:
        print(f"{args.stream} is empty")
        return

    for message_id, fields in entries:
        data = {_decode(k): _decode(v) for k, v in fields.items()}
        inner = json.loads(data.get("payload", "{}"))
        print(f"[{_decode(message_id)}] stream={inner.get('original_stream')} "
              f"retries={inner.get('retry_count')} error={inner.get('error')}")
        print(f"    payload={json.dumps(inner.get('payload'), default=str)}")


if __name__ == "__main__":
    main()
