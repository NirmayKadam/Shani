from abc import ABC, abstractmethod

class ICache(ABC):
    @abstractmethod
    def get(self, key: str) -> str:
        pass
    @abstractmethod
    def set(self, key: str, val: str, ttl: int) -> None:
        pass
    @abstractmethod
    def delete(self, key: str) -> None:
        pass
