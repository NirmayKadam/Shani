from dataclasses import dataclass

@dataclass(frozen=True)
class ImpliedVolatility:
    value: float
    def is_elevated(self, threshold: float) -> bool:
        return self.value > threshold
