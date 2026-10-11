"""
File Overview: 3.5-Year Historical Dataset Builder for Indian Options Alpha Research.
Spans January 01, 2021 to June 28, 2024 (861 trading sessions across Periods A, B, C, D).
Adheres to the strict Phase 1 institutional rules:
1. Date-dependent NSE lot sizes (75 -> 50 -> 25).
2. Time-varying RBI repo rates (4.00% -> 6.50%).
3. Synthetic forward extraction via ATM Put-Call Parity (Black-76 framework).
4. Consistent price field: CLOSE for IV inversion, surface pricing, and fills.
5. Checkpointed caching: Never redownloads cached Bhavcopies.
"""

import os
import sys
import logging
import time
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import numpy as np
import yfinance as yf

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from domains.analytics.domain.services.bsm_calculator import BsmCalculatorDomainService
from domains.analytics.domain.services.volatility_surface import VolatilitySurface
from research.models.nifty_market_rules import (
    get_nifty_lot_size,
    get_rbi_repo_rate,
    get_stt_rate,
    Black76Engine,
)
from research.data.nse_historical_options import NseBhavcopyDownloader

logger = logging.getLogger("DatasetBuilder3_5Y")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class HistoricalDatasetBuilder3_5Y:
    def __init__(self, output_dir: Optional[str] = None) -> None:
        self.base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.output_dir = output_dir or os.path.join(self.base_dir, "data", "raw")
        self.bhavcopy_dir = os.path.join(self.output_dir, "bhavcopy_cache")
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.bhavcopy_dir, exist_ok=True)
        self.downloader = NseBhavcopyDownloader(cache_dir=self.bhavcopy_dir)

    def fetch_underlying_3_5y(self) -> pd.DataFrame:
        """Fetch 3.5-year NIFTY 50 OHLCV daily data (2021 - 2024)."""
        logger.info("Fetching 3.5-year underlying OHLCV for ^NSEI from yfinance...")
        df = yf.download("^NSEI", start="2020-10-01", end="2024-07-02", progress=False)
        if df.empty:
            raise RuntimeError("Failed to download ^NSEI data from yfinance.")

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0].lower() for col in df.columns]
        else:
            df.columns = [col.lower() for col in df.columns]

        df = df.reset_index()
        df.rename(columns={"Date": "date"}, inplace=True)
        df["date"] = pd.to_datetime(df["date"]).dt.date

        # Enrich with Technical Indicators (RSI, MACD)
        close = df["close"].values
        # Standard EMA
        def _calc_ema(series: np.ndarray, window: int) -> np.ndarray:
            alpha = 2.0 / (window + 1)
            ema = np.empty_like(series)
            ema[0] = series[0]
            for i in range(1, len(series)):
                ema[i] = alpha * series[i] + (1.0 - alpha) * ema[i - 1]
            return ema

        # RSI (14)
        delta = np.diff(close, prepend=close[0])
        gains = np.where(delta > 0, delta, 0.0)
        losses = np.where(delta < 0, -delta, 0.0)
        avg_gain = _calc_ema(gains, 14)
        avg_loss = _calc_ema(losses, 14)
        rs = np.divide(avg_gain, avg_loss, out=np.ones_like(avg_gain), where=avg_loss != 0)
        df["rsi"] = np.round(100.0 - (100.0 / (1.0 + rs)), 2)

        # MACD (12, 26, 9)
        ema12 = _calc_ema(close, 12)
        ema26 = _calc_ema(close, 26)
        macd_line = ema12 - ema26
        macd_signal = _calc_ema(macd_line, 9)
        df["macd_line"] = np.round(macd_line, 2)
        df["macd_signal"] = np.round(macd_signal, 2)
        df["macd_hist"] = np.round(macd_line - macd_signal, 2)

        # Filter strictly to Jan 01, 2021 - Jun 28, 2024
        df = df[(df["date"] >= date(2021, 1, 1)) & (df["date"] <= date(2024, 6, 28))].copy()
        df.reset_index(drop=True, inplace=True)
        logger.info(f"Prepared {len(df)} daily bars for ^NSEI.")
        return df

    def download_bhavcopies_parallel(self, dates: List[date], max_workers: int = 4) -> None:
        """Download missing Bhavcopies in parallel with connection reuse."""
        missing_dates = []
        for d in dates:
            cache_file = os.path.join(self.bhavcopy_dir, f"fo_{d.strftime('%Y%m%d')}.parquet")
            if not os.path.exists(cache_file):
                missing_dates.append(d)

        logger.info(f"Total dates: {len(dates)}. Already cached: {len(dates) - len(missing_dates)}. Missing to fetch: {len(missing_dates)}")
        if not missing_dates:
            return

        success_count = 0
        def _fetch_date(target_date: date) -> bool:
            try:
                res = self.downloader.fetch_daily_fo_bhavcopy(target_date)
                return res is not None
            except Exception as e:
                logger.debug(f"Fetch error {target_date}: {e}")
                return False

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_date = {executor.submit(_fetch_date, d): d for d in missing_dates}
            for future in as_completed(future_to_date):
                if future.result():
                    success_count += 1
                if success_count % 50 == 0 and success_count > 0:
                    logger.info(f"Downloaded {success_count}/{len(missing_dates)} missing Bhavcopies...")

        logger.info(f"Bhavcopy download phase complete. Downloaded: {success_count} new archives.")

    def build_option_chains_panel(
        self,
        underlying_df: pd.DataFrame,
        strike_step: float = 50.0,
        strikes_above_below: int = 4,
    ) -> pd.DataFrame:
        """
        Builds the 3.5-year cross-sectional options panel using Black-76 and the cubic spline smile.
        """
        records: List[Dict[str, Any]] = []

        for _, row in underlying_df.iterrows():
            current_date = row["date"]
            spot = float(row["close"])
            if spot <= 0:
                continue

            r_repo = get_rbi_repo_rate(current_date)
            atm_strike = round(spot / strike_step) * strike_step
            target_strikes = [
                atm_strike + (i * strike_step)
                for i in range(-strikes_above_below, strikes_above_below + 1)
            ]

            bhav_df = self.downloader.fetch_daily_fo_bhavcopy(current_date)
            if bhav_df is None or bhav_df.empty:
                continue

            # Filter for NIFTY index options
            nifty_opts = bhav_df[
                (bhav_df.get("INSTRUMENT", "").str.strip() == "OPTIDX")
                & (bhav_df.get("SYMBOL", "").str.strip() == "NIFTY")
            ].copy()

            if nifty_opts.empty:
                continue

            # Parse expiries
            parsed_rows = []
            for _, orow in nifty_opts.iterrows():
                try:
                    exp_dt = pd.to_datetime(orow["EXPIRY_DT"]).date()
                    dte = (exp_dt - current_date).days
                    if dte >= 7:  # Minimum 7 DTE rule
                        parsed_rows.append((exp_dt, dte, orow))
                except Exception:
                    continue

            if not parsed_rows:
                continue

            # Select nearest monthly expiry >= 7 DTE
            all_expiries = sorted(set(item[0] for item in parsed_rows))
            nearest_expiry = all_expiries[0]
            expiry_dte = max(1, (nearest_expiry - current_date).days)
            t_years = expiry_dte / 365.0

            # Filter rows for target expiry
            calls_map: Dict[float, Any] = {}
            puts_map: Dict[float, Any] = {}
            for exp_dt, dte, orow in parsed_rows:
                if exp_dt == nearest_expiry:
                    stk = float(orow["STRIKE_PR"])
                    op_typ = "call" if str(orow["OPTION_TYP"]).strip() == "CE" else "put"
                    # Strictly use CLOSE price for consistent market valuation
                    close_p = float(orow.get("CLOSE", orow.get("SETTLE_PR", 0.0)))
                    contracts = float(orow.get("CONTRACTS", 0.0))

                    opt_data = {
                        "strike": stk,
                        "close_price": close_p,
                        "contracts": contracts,
                        "expiry_date": exp_dt,
                        "days_to_expiry": dte,
                    }
                    if op_typ == "call":
                        calls_map[stk] = opt_data
                    else:
                        puts_map[stk] = opt_data

            # 1. Infer Synthetic Forward from ATM Put-Call Parity
            atm_call = calls_map.get(atm_strike, {}).get("close_price", 0.0)
            atm_put = puts_map.get(atm_strike, {}).get("close_price", 0.0)
            if atm_call > 0 and atm_put > 0:
                forward_price = Black76Engine.infer_synthetic_forward(
                    call_atm=atm_call, put_atm=atm_put, strike_atm=atm_strike, expiry_years=t_years, rate=r_repo
                )
            else:
                forward_price = spot * np.exp(r_repo * t_years)

            # 2. Invert Market IVs using Black-76
            valid_strikes: List[float] = []
            valid_ivs: List[float] = []
            for k in target_strikes:
                c_data = calls_map.get(k)
                if c_data and c_data["close_price"] > 1.0:
                    c_iv = Black76Engine.solve_implied_volatility(
                        market_price=c_data["close_price"],
                        forward=forward_price,
                        strike=k,
                        expiry_years=t_years,
                        rate=r_repo,
                        option_type="call",
                    )
                    if c_iv and 0.05 <= c_iv <= 1.50:
                        valid_strikes.append(k)
                        valid_ivs.append(c_iv)
                        c_data["market_iv"] = c_iv
                        continue

                p_data = puts_map.get(k)
                if p_data and p_data["close_price"] > 1.0:
                    p_iv = Black76Engine.solve_implied_volatility(
                        market_price=p_data["close_price"],
                        forward=forward_price,
                        strike=k,
                        expiry_years=t_years,
                        rate=r_repo,
                        option_type="put",
                    )
                    if p_iv and 0.05 <= p_iv <= 1.50:
                        valid_strikes.append(k)
                        valid_ivs.append(p_iv)
                        p_data["market_iv"] = p_iv

            if len(valid_strikes) < 4:
                continue

            # 3. Fit Volatility Surface Spline
            vol_surface = VolatilitySurface(strikes=valid_strikes, ivs=valid_ivs, spot=spot)

            # 4. Compute Model Fair Values and Mispricings
            lot_size = get_nifty_lot_size(current_date, nearest_expiry)

            for k in target_strikes:
                c_data = calls_map.get(k)
                p_data = puts_map.get(k)
                if not c_data and not p_data:
                    continue

                surface_iv = vol_surface.get_surface_iv(k)
                c_mkt = c_data["close_price"] if c_data else 0.0
                p_mkt = p_data["close_price"] if p_data else 0.0
                c_vol = c_data.get("contracts", 0.0) if c_data else 0.0
                p_vol = p_data.get("contracts", 0.0) if p_data else 0.0

                # Black-76 Fair Value
                c_fair = Black76Engine.calculate_price(
                    forward=forward_price, strike=k, expiry_years=t_years, rate=r_repo, volatility=surface_iv, option_type="call"
                )
                p_fair = Black76Engine.calculate_price(
                    forward=forward_price, strike=k, expiry_years=t_years, rate=r_repo, volatility=surface_iv, option_type="put"
                )

                c_mispricing = round(c_mkt - c_fair, 4) if c_mkt > 0 else 0.0
                p_mispricing = round(p_mkt - p_fair, 4) if p_mkt > 0 else 0.0

                records.append(
                    {
                        "date": current_date,
                        "spot": spot,
                        "forward": round(forward_price, 2),
                        "strike": k,
                        "days_to_expiry": expiry_dte,
                        "expiry_years": t_years,
                        "expiry_date": nearest_expiry,
                        "lot_size": lot_size,
                        "rbi_repo_rate": r_repo,
                        "surface_iv": surface_iv,
                        "call_mkt_price": c_mkt,
                        "call_fair_price": round(c_fair, 4),
                        "call_mispricing": c_mispricing,
                        "call_contracts": c_vol,
                        "put_mkt_price": p_mkt,
                        "put_fair_price": round(p_fair, 4),
                        "put_mispricing": p_mispricing,
                        "put_contracts": p_vol,
                        "is_atm": (k == atm_strike),
                    }
                )

        options_df = pd.DataFrame(records)
        logger.info(f"Built options panel with {len(options_df)} strike records across {options_df['date'].nunique()} trading dates.")
        return options_df

    def run_all(self) -> None:
        logger.info("=" * 70)
        logger.info("STARTING 3.5-YEAR DATASET COLLECTION & PANEL COMPILATION")
        logger.info("=" * 70)

        # 1. Underlying OHLCV
        ohlcv_df = self.fetch_underlying_3_5y()
        ohlcv_path = os.path.join(self.output_dir, "nifty_3_5y_daily_ohlcv.parquet")
        ohlcv_df.to_parquet(ohlcv_path, index=False)
        ohlcv_df.to_csv(os.path.join(self.output_dir, "nifty_3_5y_daily_ohlcv.csv"), index=False)

        # 2. Parallel Bhavcopy Archive Retrieval
        dates_list = ohlcv_df["date"].tolist()
        self.download_bhavcopies_parallel(dates_list, max_workers=4)

        # 3. Construct Options Panel
        options_df = self.build_option_chains_panel(ohlcv_df)
        options_path = os.path.join(self.output_dir, "nifty_3_5y_option_chains.parquet")
        options_df.to_parquet(options_path, index=False)
        options_df.to_csv(os.path.join(self.output_dir, "nifty_3_5y_option_chains.csv"), index=False)

        logger.info(f"[SUCCESS] 3.5-Year Data Panel saved successfully to: {options_path}")


if __name__ == "__main__":
    builder = HistoricalDatasetBuilder3_5Y()
    builder.run_all()
