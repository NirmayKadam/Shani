from domains.analytics.application.ports.interface.outbound.i_cache import i_cache

class redis_adapter(i_cache):
    def __init__(self, url: str = None):
        self._url = url
    def get(self, key: str) -> str: return ""
    def set(self, key: str, val: str, ttl: int) -> None: pass
    def delete(self, key: str) -> None: pass
