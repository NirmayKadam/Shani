from abc import ABC, abstractmethod

class IDedupStore(ABC):
    @abstractmethod
    def is_seen(self, article_id: str) -> bool:
        pass
    @abstractmethod
    def mark_seen(self, article_id: str) -> None:
        pass
