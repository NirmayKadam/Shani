from abc import ABC, abstractmethod

class IModelStore(ABC):
    @abstractmethod
    def save_model(self, symbol: str, path: str) -> None:
        pass
    @abstractmethod
    def load_model(self, symbol: str) -> str:
        pass
