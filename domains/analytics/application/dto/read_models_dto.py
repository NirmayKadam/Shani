"""
File Overview: Data models and calculation logic for analytics read-model snapshots.

All Functions/Classes:
- OptionChainSummaryReadModel: Pydantic schema for option chain snapshots. Take JSON data and send to validated object.
- compute_pcr: Logic to calculate Put-Call Ratio. Take option chain dict and send PCR summary stats.

Endpoints/APIs:
- None.

Database Tables:
- None.
"""
from pydantic import BaseModel, Field



class OptionChainSummaryDTO(BaseModel):
    spot_price: float = 0.0
    expiry_dates: list[str] = Field(default_factory=list)
    summary: dict = Field(default_factory=dict)
    fetched_at: str = ""
    chains: dict = Field(default_factory=dict)


def compute_pcr(option_chain: dict) -> dict:
    """Put-call ratio of the nearest live expiry.

    `pcr` is the standard open-interest ratio (put OI / call OI); `volume_pcr` is the
    traded-volume ratio. Either is None when the call side is zero, which means "no data",
    not "extremely bullish".
    """
    from shared.utils.market_time import nearest_expiry

    chains = option_chain.get("chains") or {}
    expiry = nearest_expiry(chains.keys()) or (min(chains) if chains else None)

    totals = {"CE": {"oi": 0, "volume": 0}, "PE": {"oi": 0, "volume": 0}}
    for tick in chains.get(expiry, []) if expiry else []:
        side = totals.get(tick.get("type"))
        if side is not None:
            side["oi"] += int(tick.get("oi", 0) or 0)
            side["volume"] += int(tick.get("volume", 0) or 0)

    def ratio(field: str):
        calls = totals["CE"][field]
        return round(totals["PE"][field] / calls, 4) if calls > 0 else None

    return {
        "pcr": ratio("oi"),
        "volume_pcr": ratio("volume"),
        "expiry": expiry,
        "ce_volume": totals["CE"]["volume"],
        "pe_volume": totals["PE"]["volume"],
        "ce_oi": totals["CE"]["oi"],
        "pe_oi": totals["PE"]["oi"],
    }
