from dataclasses import dataclass

@dataclass(frozen=True)
class Symbol:
    value: str
    def __post_init__(self):
        if not self.value.isupper():
            raise ValueError("Symbol must be uppercase")
