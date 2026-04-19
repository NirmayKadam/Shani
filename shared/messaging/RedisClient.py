import os
import redis

def get_redis_sync():
    """
    Returns a sync Redis client connection using the environment variable REDIS_URL.
    """
    url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    return redis.Redis.from_url(url, decode_responses=True)
