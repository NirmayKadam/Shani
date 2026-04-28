"""
File Overview: Value object representing a derivatives expiry date.

All Functions/Classes:
- Expiry: Data structure for expiry dates. Take date and send time-to-maturity logic.
- days_to_expiry: Calculate time delta. Take current date and send day count.

Endpoints/APIs: None

Database Tables: None
"""
from dataclasses import dataclass
from datetime import date

@dataclass(frozen=True)
class Expiry:
    date_val: date
    def days_to_expiry(self, current_date: date) -> int:
        return (self.date_val - current_date).days
