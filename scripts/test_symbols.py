
import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from shared.utils.symbol_validator import SymbolValidator

symbols = ["NIFTY", "BANKNIFTY", "RELIANCE", "INFY", "HDFCBANK", "TCS", "ICICIBANK"]

print("Testing SymbolValidator.get_clean_symbol:")
for sym in symbols:
    clean = SymbolValidator.get_clean_symbol(sym)
    print(f"'{sym}' -> '{clean}'")

print("\nTesting SymbolValidator.validate:")
for sym in symbols:
    valid = SymbolValidator.validate(sym)
    print(f"'{sym}' -> {valid}")
