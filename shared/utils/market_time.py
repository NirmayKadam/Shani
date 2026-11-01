"""
File Overview: Shared helpers for option time-to-expiry and the risk-free rate.

All Functions/Classes:
- parse_expiry: Parse an expiry string (YYYY-MM-DD) into a date. Data: string -> date or None.
- years_to_expiry: Fractional years from now to the NSE expiry settlement time. Data: expiry -> float.
- nearest_expiry: Earliest expiry that has not yet settled. Data: expiry strings -> string or None.
- risk_free_rate_for: Annual risk-free rate (decimal) for a cleaned symbol. Data: symbol -> float.

Endpoints/APIs: None

Database Tables: None
"""
from datetime import date, datetime, time, timezone
from typing import Iterable, Optional

from app.config.settings import get_settings
from shared.constants import INDEX_SYMBOLS

# NSE derivatives settle at 15:30 IST = 10:00 UTC on the expiry date.
_SETTLEMENT_UTC = time(10, 0, tzinfo=timezone.utc)
_SECONDS_PER_YEAR = 365.0 * 24 * 3600
# Floor so an option on its expiry afternoon still has a positive time to maturity (1 minute).
_MIN_YEARS = 60.0 / _SECONDS_PER_YEAR


def parse_expiry(expiry: str) -> Optional[date]:
    try:
        return datetime.strptime(expiry, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _settlement(expiry_date: date) -> datetime:
    return datetime.combine(expiry_date, _SETTLEMENT_UTC)


def years_to_expiry(expiry: str, now: Optional[datetime] = None) -> Optional[float]:
    """Fractional years until settlement, or None for an unparseable expiry."""
    expiry_date = parse_expiry(expiry)
    if expiry_date is None:
        return None
    now = now or datetime.now(timezone.utc)
    seconds = (_settlement(expiry_date) - now).total_seconds()
    return max(seconds / _SECONDS_PER_YEAR, _MIN_YEARS)


def nearest_expiry(expiries: Iterable[str], now: Optional[datetime] = None) -> Optional[str]:
    """The earliest expiry whose settlement time is still in the future."""
    now = now or datetime.now(timezone.utc)
    live = sorted(
        (d, e) for e in set(expiries)
        if (d := parse_expiry(e)) is not None and _settlement(d) > now
    )
    return live[0][1] if live else None


def risk_free_rate_for(symbol_clean: str) -> float:
    """Annual risk-free rate as a decimal: INR for NSE/BSE symbols and indices, else USD."""
    settings = get_settings()
    symbol_clean = (symbol_clean or "").upper()
    is_indian = (
        symbol_clean.endswith((".NS", ".BO"))
        or symbol_clean in INDEX_SYMBOLS
    )
    rate_pct = settings.DefaultRiskFreeRateInr if is_indian else settings.DefaultRiskFreeRateUsd
    return rate_pct / 100.0
