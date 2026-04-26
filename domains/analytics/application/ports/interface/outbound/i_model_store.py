from abc import ABC, abstractmethod

class i_model_store(ABC):
    @abstractmethod
    def save_model(self, symbol: str, path: str) -> None:
        pass
    @abstractmethod
    def load_model(self, symbol: str) -> str:
        pass
