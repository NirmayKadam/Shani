from dataclasses import dataclass
from datetime import date

@dataclass(frozen=True)
class Expiry:
    date_val: date
    def days_to_expiry(self, current_date: date) -> int:
        return (self.date_val - current_date).days
