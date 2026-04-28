import logging
import yfinance as yf
from functools import lru_cache

logger = logging.getLogger(__name__)

class SymbolValidator:
    """
    Utility to validate if a ticker symbol exists and is supported.
    Strictsly limits validation to the Indian stock market (NSE/BSE).
    Uses yfinance for verification and handles result caching.
    """

    @staticmethod
    @lru_cache(maxsize=1000)
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
            # Allow NIFTY, BANKNIFTY etc or explicit yfinance indices like ^NSEI
            return True

        # 1. Check if it's already an Indian market symbol
        if symbol_upper.endswith(".NS") or symbol_upper.endswith(".BO"):
            try:
                ticker = yf.Ticker(symbol_upper)
                hist = ticker.history(period="1d")
                if not hist.empty:
                    return True
            except Exception:
                pass
            return False

        # 2. Heuristic for Indian stocks: If no suffix, try .NS then .BO
        if symbol_upper.isalnum():
            # Try NSE first (default)
            try:
                ticker = yf.Ticker(f"{symbol_upper}.NS")
                hist = ticker.history(period="1d")
                if not hist.empty:
                    return True
            except Exception:
                pass
                
            # Try BSE
            try:
                ticker = yf.Ticker(f"{symbol_upper}.BO")
                hist = ticker.history(period="1d")
                if not hist.empty:
                    return True
            except Exception:
                pass
                
        # 3. Reject everything else (foreign stocks, etc.)
        return False

    @staticmethod
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
            
        # 1. Try to resolve bare symbol to Indian market
        if symbol_upper.isalnum():
            # Try NSE
            try:
                ticker = yf.Ticker(f"{symbol_upper}.NS")
                hist = ticker.history(period="1d")
                if not hist.empty:
                    return f"{symbol_upper}.NS"
            except:
                pass
                
            # Try BSE
            try:
                ticker = yf.Ticker(f"{symbol_upper}.BO")
                hist = ticker.history(period="1d")
                if not hist.empty:
                    return f"{symbol_upper}.BO"
            except:
                pass
            
        return symbol_upper
