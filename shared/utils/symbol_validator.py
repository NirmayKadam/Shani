import logging
import yfinance as yf
from functools import lru_cache

Logger = logging.getLogger(__name__)

class SymbolValidator:
    """
    Utility to validate if a ticker symbol exists and is supported.
    Uses yfinance for verification and handles result caching.
    """

    @staticmethod
    @lru_cache(maxsize=1000)
    def validate(symbol: str) -> bool:
        """
        Check if a symbol is valid by attempting a light fetch from yfinance.
        """
        if not symbol:
            return False
            
        symbol_upper = symbol.strip().upper()
        
        # 0. Allow known indices
        from shared.constants import INDEX_SYMBOLS
        if symbol_upper in INDEX_SYMBOLS:
            return True

        # 1. Try exactly as provided
        try:
            ticker = yf.Ticker(symbol_upper)
            hist = ticker.history(period="1d")
            if not hist.empty:
                return True
        except Exception:
            pass

        # 2. Heuristic for NSE symbols: if not explicitly provided with .NS and likely an Indian ticker (letters only)
        if not symbol_upper.endswith(".NS") and symbol_upper.isalpha():
             try:
                # Use a specific ticker to avoid lru_cache side effects during validation
                ticker = yf.Ticker(f"{symbol_upper}.NS")
                hist = ticker.history(period="1d")
                if not hist.empty:
                    return True
             except Exception:
                pass
                
        return False

    @staticmethod
    def get_clean_symbol(symbol: str) -> str:
        """
        Returns the formatted version of the symbol (e.g., adding .NS if it's an Indian stock).
        """
        symbol_upper = symbol.strip().upper()
        if symbol_upper.endswith(".NS") or "^" in symbol_upper:
            return symbol_upper
            
        # If it's a known NSE index, return as is (mapped later in fetcher)
        from shared.constants import INDEX_SYMBOLS
        if symbol_upper in INDEX_SYMBOLS:
            return symbol_upper
            
        # Try to see if it's an Indian stock without .NS
        try:
            ticker = yf.Ticker(f"{symbol_upper}.NS")
            # history is much more reliable than fast_info
            hist = ticker.history(period="1d")
            if not hist.empty:
                return f"{symbol_upper}.NS"
        except:
            pass
            
        return symbol_upper
