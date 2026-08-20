"""
File Overview: Indian Derivatives Market Friction & Dynamic Slippage Model.
Calculates all statutory trading costs (STT, NSE exchange charges, Stamp Duty, GST, SEBI fee)
and determines the dynamic epsilon threshold (epsilon_t) required for statistical arbitrage execution.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FrictionEstimate:
    """Detailed breakdown of trading costs for an option order."""
    premium: float
    lot_size: int
    stt: float              # Securities Transaction Tax (Sell side)
    exchange_fee: float     # NSE exchange turnover fee
    stamp_duty: float       # Stamp duty (Buy side)
    sebi_fee: float         # SEBI turnover charge
    brokerage: float        # Broker commission
    gst: float              # 18% GST on (Brokerage + Exchange fee)
    spread_cost: float      # Half-spread market impact per unit
    total_one_way: float    # Sum per unit
    total_round_trip: float # Total friction per unit for complete round-trip trade


class IndianOptionsFrictionModel:
    """
    Standardized statutory friction and transaction cost model for National Stock Exchange (NSE)
    index derivatives (NIFTY / BANKNIFTY).
    """

    # Statutory base rates as prescribed by SEBI and Government of India (2024 revised rates)
    DEFAULT_STT_SELL_RATE: float = 0.000625        # 0.0625% on option sell premium turnover
    DEFAULT_EXCHANGE_CHARGE_RATE: float = 0.000500 # 0.050% NSE transaction charge
    DEFAULT_STAMP_DUTY_BUY_RATE: float = 0.000030  # 0.003% on option buy turnover
    DEFAULT_SEBI_TURNOVER_RATE: float = 0.000001   # ₹10 per ₹1 Crore turnover
    DEFAULT_GST_RATE: float = 0.18                 # 18% GST on brokerage + exchange charges

    def __init__(
        self,
        brokerage_per_order: float = 20.0,
        default_lot_size: int = 50,
        min_spread_pct: float = 0.005,
        stt_sell_rate: Optional[float] = None,
        exchange_charge_rate: Optional[float] = None,
        stamp_duty_buy_rate: Optional[float] = None,
        sebi_turnover_rate: Optional[float] = None,
        gst_rate: Optional[float] = None,
        multiplier: float = 1.0,
    ) -> None:
        """
        Args:
            brokerage_per_order: Fixed rupee brokerage per executed order (e.g. ₹20).
            default_lot_size: Contract lot size (50 for NIFTY, 15 for BANKNIFTY).
            min_spread_pct: Default half-spread estimate as fraction of premium if bid/ask unavailable.
            stt_sell_rate: Custom STT sell rate.
            exchange_charge_rate: Custom exchange charge rate.
            stamp_duty_buy_rate: Custom stamp duty rate.
            sebi_turnover_rate: Custom SEBI turnover charge.
            gst_rate: Custom GST rate.
            multiplier: Uniform scaling factor for stress-testing transaction frictions.
        """
        mult = float(multiplier)
        self.brokerage_per_order = float(brokerage_per_order) * mult
        self.default_lot_size = int(default_lot_size)
        self.min_spread_pct = float(min_spread_pct) * mult
        
        self.stt_sell_rate = (self.DEFAULT_STT_SELL_RATE if stt_sell_rate is None else float(stt_sell_rate)) * mult
        self.exchange_charge_rate = (self.DEFAULT_EXCHANGE_CHARGE_RATE if exchange_charge_rate is None else float(exchange_charge_rate)) * mult
        self.stamp_duty_buy_rate = (self.DEFAULT_STAMP_DUTY_BUY_RATE if stamp_duty_buy_rate is None else float(stamp_duty_buy_rate)) * mult
        self.sebi_turnover_rate = (self.DEFAULT_SEBI_TURNOVER_RATE if sebi_turnover_rate is None else float(sebi_turnover_rate)) * mult
        self.gst_rate = self.DEFAULT_GST_RATE if gst_rate is None else float(gst_rate)

    def estimate(
        self,
        premium: float,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
        lot_size: Optional[int] = None,
        is_sell: bool = False,
    ) -> FrictionEstimate:
        """
        Compute full friction breakdown for an option order at a given premium.
        """
        if premium <= 0:
            return FrictionEstimate(
                premium=0.0,
                lot_size=lot_size or self.default_lot_size,
                stt=0.0,
                exchange_fee=0.0,
                stamp_duty=0.0,
                sebi_fee=0.0,
                brokerage=0.0,
                gst=0.0,
                spread_cost=0.0,
                total_one_way=0.0,
                total_round_trip=0.0,
            )

        lots = lot_size if lot_size is not None else self.default_lot_size

        # 1. Spread impact
        if bid is not None and ask is not None and ask >= bid:
            spread_per_unit = (ask - bid) / 2.0
        else:
            spread_per_unit = premium * self.min_spread_pct

        # 2. Statutory percentages per unit of premium
        stt_unit = (premium * self.stt_sell_rate) if is_sell else 0.0
        exchange_unit = premium * self.exchange_charge_rate
        stamp_unit = (premium * self.stamp_duty_buy_rate) if not is_sell else 0.0
        sebi_unit = premium * self.sebi_turnover_rate

        # 3. Fixed broker charge per unit
        brokerage_unit = self.brokerage_per_order / float(lots) if lots > 0 else 0.0

        # 4. GST on taxable services
        gst_unit = (brokerage_unit + exchange_unit) * self.gst_rate

        # Total one-way cost per unit
        total_one_way = (
            stt_unit
            + exchange_unit
            + stamp_unit
            + sebi_unit
            + brokerage_unit
            + gst_unit
            + spread_per_unit
        )

        # Conservative round-trip cost (Buy + Sell legs)
        rt_stt = premium * self.stt_sell_rate
        rt_stamp = premium * self.stamp_duty_buy_rate
        rt_exchange = 2.0 * exchange_unit
        rt_sebi = 2.0 * sebi_unit
        rt_brokerage = 2.0 * brokerage_unit
        rt_gst = 2.0 * gst_unit
        rt_spread = 2.0 * spread_per_unit

        total_round_trip = (
            rt_stt
            + rt_stamp
            + rt_exchange
            + rt_sebi
            + rt_brokerage
            + rt_gst
            + rt_spread
        )

        return FrictionEstimate(
            premium=float(round(premium, 4)),
            lot_size=lots,
            stt=float(round(stt_unit, 4)),
            exchange_fee=float(round(exchange_unit, 4)),
            stamp_duty=float(round(stamp_unit, 4)),
            sebi_fee=float(round(sebi_unit, 6)),
            brokerage=float(round(brokerage_unit, 4)),
            gst=float(round(gst_unit, 4)),
            spread_cost=float(round(spread_per_unit, 4)),
            total_one_way=float(round(total_one_way, 4)),
            total_round_trip=float(round(total_round_trip, 4)),
        )

    def compute_epsilon(
        self,
        premium: float,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
        lot_size: Optional[int] = None,
        buffer_multiplier: float = 1.5,
    ) -> float:
        """
        Compute dynamic threshold epsilon_t = round_trip_cost * buffer_multiplier.
        A trade is only signaled if theoretical PDE mispricing |C_market - C_PDE| > epsilon_t.
        """
        est = self.estimate(premium=premium, bid=bid, ask=ask, lot_size=lot_size)
        return float(round(est.total_round_trip * buffer_multiplier, 4))
