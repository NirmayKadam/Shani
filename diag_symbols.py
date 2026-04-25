import yfinance as yf
import sys
import os

# Add current dir to path to import shared
sys.path.append(os.getcwd())

from shared.utils.symbol_validator import SymbolValidator

def test_symbol(symbol):
    print(f"\n--- Testing symbol: {symbol} ---")
    clean = SymbolValidator.get_clean_symbol(symbol)
    print(f"get_clean_symbol('{symbol}') -> '{clean}'")
    
    valid = SymbolValidator.validate(symbol)
    print(f"validate('{symbol}') -> {valid}")
    
    print("Direct yfinance check:")
    for s in [symbol, f"{symbol}.NS"]:
        try:
            ticker = yf.Ticker(s)
            hist = ticker.history(period="1d")
            print(f"  Ticker('{s}').history: {not hist.empty} (size: {len(hist)})")
            # print(f"  Ticker('{s}').fast_info: {ticker.fast_info}")
            if hasattr(ticker, 'fast_info'):
                try:
                    price = ticker.fast_info.get('last_price')
                    print(f"  Ticker('{s}').fast_info.last_price: {price}")
                except Exception as e:
                    print(f"  Ticker('{s}').fast_info error: {e}")
        except Exception as e:
            print(f"  Ticker('{s}') error: {e}")

if __name__ == "__main__":
    for sym in ["JIOFIN", "RELIANCE", "AAPL", "ZOMATO"]:
        test_symbol(sym)
