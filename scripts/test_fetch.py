import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from domains.ingestion.infrastructure.adapters.outbound.nse_api_adapter import NseApiAdapter, _NSE_API_HEADERS

def custom_parse_nse_date(date_str: str) -> str:
    months = {"Jan":"01","Feb":"02","Mar":"03","Apr":"04","May":"05","Jun":"06","Jul":"07","Aug":"08","Sep":"09","Oct":"10","Nov":"11","Dec":"12"}
    try:
        d, m, y = date_str.split("-")
        return f"{y}-{months[m.capitalize()]}-{d.zfill(2)}"
    except Exception as e:
        return None

def custom_parse_option_chain(symbol: str, data: dict) -> dict:
    records = data.get("records", {})
    underlying = records.get("underlyingValue", 0)
    expiry_dates_raw = records.get("expiryDates", [])
    all_data = records.get("data", [])

    chains = {}
    for row in all_data:
        strike = row.get("strikePrice")
        # Try both expiryDate and expiryDates keys
        expiry_raw = row.get("expiryDate") or row.get("expiryDates", "")
        expiry = custom_parse_nse_date(expiry_raw)
        if not strike or not expiry:
            continue

        if expiry not in chains:
            chains[expiry] = []
        for opt_key in ["CE", "PE"]:
            opt = row.get(opt_key)
            if opt:
                lp = opt.get("lastPrice", 0)
                if lp > 0:
                    chains[expiry].append({
                        "strike": float(strike), "type": opt_key, "last_price": float(lp),
                        "oi": int(opt.get("openInterest", 0)), "volume": int(opt.get("totalTradedVolume", 0)),
                        "iv": float(opt.get("impliedVolatility", 0.0)), "expiry": expiry
                    })
    return {"symbol": symbol.upper(), "spot_price": float(underlying), "expiry_dates": expiry_dates_raw, "chains": chains}

async def test():
    adapter = NseApiAdapter()
    try:
        session = await adapter._ensure_session()
        await adapter._soft_initialise("TCS")
        
        info_url = "https://www.nseindia.com/api/option-chain-contract-info?symbol=TCS"
        async with session.get(info_url, headers=_NSE_API_HEADERS) as resp:
            info_data = await resp.json()
            expiries = info_data.get("expiryDates", [])
            
        if expiries:
            v3_url = f"https://www.nseindia.com/api/option-chain-v3?type=Equity&symbol=TCS&expiry={expiries[0]}"
            async with session.get(v3_url, headers=_NSE_API_HEADERS) as resp:
                if resp.status == 200:
                    raw_v3 = await resp.json()
                    v3_ticks = raw_v3.get("data", []) or raw_v3.get("records", {}).get("data", [])
                    
                    parsed = custom_parse_option_chain("TCS", {"records": {"underlyingValue": 2256.0, "expiryDates": expiries, "data": v3_ticks}})
                    print(f"Parsed keys: {parsed.keys()}")
                    chains = parsed.get("chains", {})
                    print(f"Chains keys: {list(chains.keys())}")
                    for exp, ticks in chains.items():
                        print(f"  {exp}: {len(ticks)} ticks")
    finally:
        await adapter.close()

if __name__ == "__main__":
    asyncio.run(test())
