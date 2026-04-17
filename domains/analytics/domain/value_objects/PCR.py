from dataclasses import dataclass

@dataclass(frozen=True)
class PCR:
    value: float
    def interpretation(self) -> str:
        if self.value > 1.2: return "BULLISH"
        if self.value < 0.8: return "BEARISH"
        return "NEUTRAL"
