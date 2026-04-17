from dataclasses import dataclass

@dataclass(frozen=True)
class Polarity:
    value: float
    def label(self) -> str:
        if self.value > 0.1: return "BULLISH"
        if self.value < -0.1: return "BEARISH"
        return "NEUTRAL"
