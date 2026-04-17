from domains.analytics.ports.outbound.ICache import ICache

class RedisAdapter(ICache):
    def get(self, key: str) -> str: return ""
    def set(self, key: str, val: str, ttl: int) -> None: pass
    def delete(self, key: str) -> None: pass
