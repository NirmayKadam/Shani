import redis
from domains.ingestion.application.ports.interface.outbound.i_dedup_store import i_dedup_store

class redis_dedup_adapter(i_dedup_store):
    def __init__(self, redis_url: str):
        self.r = redis.Redis.from_url(redis_url)
    
    def is_seen(self, article_id: str) -> bool:
        return self.r.exists(article_id) == 1
        
    def mark_seen(self, article_id: str) -> None:
        self.r.set(article_id, "1", ex=86400) # 24h
