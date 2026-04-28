"""
File Overview: Value object defining supported stock exchanges (NSE, BSE).

All Functions/Classes:
- Exchange: Enumeration of trading venues. Take exchange code and send domain label.

Endpoints/APIs: None

Database Tables: None
"""
from enum import Enum

class Exchange(Enum):
    NSE = "NSE"
    BSE = "BSE"
