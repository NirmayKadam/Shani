from domains.analytics.application.ports.interface.outbound.ICache import ICache

class RedisAdapter(ICache):
    def __init__(self, url: str = None):
        self._url = url
    def get(self, key: str) -> str: return ""
    def set(self, key: str, val: str, ttl: int) -> None: pass
    def delete(self, key: str) -> None: pass
