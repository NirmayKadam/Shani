"""
File Overview: Utility for validating and formatting Indian stock market ticker symbols (NSE/BSE).

All Functions/Classes:
- SymbolValidator (class): Provides static methods to validate symbols and clean them with Indian suffixes (.NS/.BO). Data: Symbol String -> Boolean/Cleaned Symbol.

Endpoints/APIs:
- External: yfinance API for ticker verification.

Database Tables:
- None.
"""
import functools
import logging
import threading
import time

import yfinance as yf

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 24 * 3600
_CACHE_MAX_ENTRIES = 2000


class _NetworkUnavailable(Exception):
    """yfinance could not be reached, so the answer is unknown and must not be cached."""


def _yf_has_history(yf_symbol: str) -> bool:
    try:
        return not yf.Ticker(yf_symbol).history(period="1d").empty
    except Exception as exc:
        raise _NetworkUnavailable(str(exc))


def _ttl_cached(fallback):
    """Thread-safe TTL cache that stores only definite answers.

    When the wrapped function raises _NetworkUnavailable the fallback(symbol) value is returned
    without caching, so a transient yfinance error cannot pin a valid symbol as invalid.
    """
    def decorator(fn):
        cache: dict[str, tuple[object, float]] = {}
        lock = threading.Lock()

        @functools.wraps(fn)
        def wrapper(symbol: str):
            now = time.monotonic()
            with lock:
                hit = cache.get(symbol)
                if hit and now - hit[1] < _CACHE_TTL_SECONDS:
                    return hit[0]
            try:
                value = fn(symbol)
            except _NetworkUnavailable as exc:
                logger.warning("Symbol lookup for %s inconclusive (not cached): %s", symbol, exc)
                return fallback(symbol)
            with lock:
                if len(cache) >= _CACHE_MAX_ENTRIES:
                    cache.pop(next(iter(cache)))
                cache[symbol] = (value, now)
            return value

        wrapper.cache_clear = lambda: cache.clear()
        return wrapper
    return decorator


class SymbolValidator:
    """
    Utility to validate if a ticker symbol exists and is supported.
    Strictly limits validation to the Indian stock market (NSE/BSE).
    Uses local mapping for speed, yfinance for fallback verification.
    """

    _LOCAL_NSE_MAP = {
        "NIFTY": "NIFTY",
        "BANKNIFTY": "BANKNIFTY",
        "FINNIFTY": "FINNIFTY",
        "RELIANCE": "RELIANCE.NS",
        "TCS": "TCS.NS",
        "INFY": "INFY.NS",
        "HDFCBANK": "HDFCBANK.NS",
        "ICICIBANK": "ICICIBANK.NS",
        "BHARTIARTL": "BHARTIARTL.NS",
        "SBIN": "SBIN.NS",
        "LICI": "LICI.NS",
        "ITC": "ITC.NS",
        "HINDUNILVR": "HINDUNILVR.NS",
        "LT": "LT.NS",
        "BAJFINANCE": "BAJFINANCE.NS"
    }

    @staticmethod
    @_ttl_cached(fallback=lambda symbol: False)
    def validate(symbol: str) -> bool:
        """
        Check if a symbol is valid and from the Indian market.
        Valid formats: Ticker.NS, Ticker.BO, or INDEX_SYMBOLS.
        """
        if not symbol:
            return False
            
        symbol_upper = symbol.strip().upper()
        
        # 0. Allow known indices
        from shared.constants import INDEX_SYMBOLS
        if symbol_upper in INDEX_SYMBOLS or "^" in symbol_upper:
            return True

        # 0.5 Check local map
        if symbol_upper in SymbolValidator._LOCAL_NSE_MAP:
            return True

        # 0.6 Check dynamic instruments catalog
        try:
            from domains.analytics.api.instruments_loader import instruments_catalog
            if instruments_catalog.is_valid_symbol(symbol_upper):
                return True
        except Exception:
            pass

        # 1. Check if it's already an Indian market symbol
        if symbol_upper.endswith(".NS") or symbol_upper.endswith(".BO"):
            return _yf_has_history(symbol_upper)

        # 2. Heuristic for Indian stocks: If no suffix, try .NS then .BO
        if symbol_upper.isalnum():
            return _yf_has_history(f"{symbol_upper}.NS") or _yf_has_history(f"{symbol_upper}.BO")

        # 3. Reject everything else (foreign stocks, etc.)
        return False

    @staticmethod
    @_ttl_cached(fallback=lambda symbol: (symbol or "").strip().upper())
    def get_clean_symbol(symbol: str) -> str:
        """
        Returns the Indian market formatted version of the symbol (e.g., adding .NS).
        """
        if not symbol:
            return ""
            
        symbol_upper = symbol.strip().upper()
        
        # 0. Already has correct suffix or is an index
        from shared.constants import INDEX_SYMBOLS
        if symbol_upper.endswith(".NS") or symbol_upper.endswith(".BO") or symbol_upper in INDEX_SYMBOLS or "^" in symbol_upper:
            return symbol_upper
            
        # 0.5 Check local map (Fastest)
        if symbol_upper in SymbolValidator._LOCAL_NSE_MAP:
            return SymbolValidator._LOCAL_NSE_MAP[symbol_upper]

        # 0.6 Check dynamic instruments catalog
        try:
            from domains.analytics.api.instruments_loader import instruments_catalog
            if instruments_catalog.is_valid_symbol(symbol_upper):
                from shared.constants import INDEX_SYMBOLS
                if symbol_upper not in INDEX_SYMBOLS:
                    return f"{symbol_upper}.NS"
                return symbol_upper
        except Exception:
            pass
            
        # 1. Try to resolve bare symbol to Indian market (Slow fallback)
        if symbol_upper.isalnum():
            if _yf_has_history(f"{symbol_upper}.NS"):
                return f"{symbol_upper}.NS"
            if _yf_has_history(f"{symbol_upper}.BO"):
                return f"{symbol_upper}.BO"

        return symbol_upper
