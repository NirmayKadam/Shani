"""
File Overview: Historical Data Ingestion & Option Chain Dataset Builder for NIFTY 50.
Fetches underlying index OHLCV, India VIX time series, and constructs continuous
option pricing panels for backtesting mathematical PDE strategies against retail technicals.
"""

import os
import sys
import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

# Ensure root directory is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from domains.analytics.domain.services.technical_indicators_engine import TechnicalIndicatorsEngine
from domains.analytics.domain.services.bsm_calculator import BsmCalculatorDomainService
from domains.analytics.domain.services.volatility_surface import VolatilitySurface
from research.data.nse_historical_options import NseBhavcopyDownloader

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class HistoricalDataCollector:
    """
    Collects and prepares empirical dataset for quantitative derivatives backtesting.
    """

    DEFAULT_OUTPUT_DIR = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "raw")
    )

    def __init__(self, output_dir: Optional[str] = None) -> None:
        self.output_dir = output_dir or self.DEFAULT_OUTPUT_DIR
        os.makedirs(self.output_dir, exist_ok=True)

    def fetch_underlying_ohlcv(
        self,
        symbol: str = "^NSEI",
        days: int = 250,
    ) -> pd.DataFrame:
        """
        Fetch daily OHLCV for NIFTY 50 index using yfinance.
        """
        import yfinance as yf

        logger.info(f"Fetching {days} days of underlying data for {symbol}...")
        ticker = yf.Ticker(symbol)
        
        # Use a fixed historical window (e.g. ending Mid-2024) to ensure NSE Bhavcopy 
        # archive URLs are perfectly stable and available.
        end_date = datetime(2024, 6, 30).date()
        start_date = end_date - timedelta(days=int(days * 1.5))  # Account for weekends/holidays

        df = ticker.history(start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"))
        if df.empty:
            raise ValueError(f"No price data retrieved for {symbol} from yfinance")

        # Standardize columns
        df.reset_index(inplace=True)
        date_col = "Date" if "Date" in df.columns else df.columns[0]
        df["Date"] = pd.to_datetime(df[date_col]).dt.tz_localize(None).dt.date
        df = df[["Date", "Open", "High", "Low", "Close", "Volume"]].sort_values("Date").reset_index(drop=True)
        df.rename(
            columns={
                "Date": "date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            },
            inplace=True,
        )

        logger.info(f"Retrieved {len(df)} daily bars for {symbol}")
        return df.tail(days).reset_index(drop=True)

    def fetch_india_vix(self, days: int = 250) -> pd.DataFrame:
        """
        Fetch India VIX time series for volatility regime classification.
        """
        import yfinance as yf

        logger.info("Fetching India VIX history (^INDIAVIX)...")
        ticker = yf.Ticker("^INDIAVIX")
        
        # Consistent fixed historical window
        end_date = datetime(2024, 6, 30).date()
        start_date = end_date - timedelta(days=int(days * 1.5))

        df = ticker.history(start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"))
        if df.empty:
            logger.warning("India VIX fetch returned empty; defaulting to baseline vol")
            return pd.DataFrame(columns=["date", "vix_close"])

        df.reset_index(inplace=True)
        date_col = "Date" if "Date" in df.columns else df.columns[0]
        df["date"] = pd.to_datetime(df[date_col]).dt.tz_localize(None).dt.date
        df = df[["date", "Close"]].rename(columns={"Close": "vix_close"}).sort_values("date").reset_index(drop=True)
        return df.tail(days).reset_index(drop=True)

    def enrich_with_technical_indicators(self, ohlcv_df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute RSI, MACD, Bollinger Bands, ATR, EMA, SMA across historical bars.
        """
        df = ohlcv_df.copy()
        closes = df["close"].tolist()
        highs = df["high"].tolist()
        lows = df["low"].tolist()

        rsi_list = [None] * len(df)
        macd_list = [None] * len(df)
        macd_signal_list = [None] * len(df)
        macd_hist_list = [None] * len(df)
        bb_upper = [None] * len(df)
        bb_middle = [None] * len(df)
        bb_lower = [None] * len(df)
        atr_list = [None] * len(df)

        for i in range(len(df)):
            sub_closes = closes[: i + 1]
            sub_highs = highs[: i + 1]
            sub_lows = lows[: i + 1]

            # RSI
            if len(sub_closes) >= 15:
                rsi_list[i] = TechnicalIndicatorsEngine.calculate_rsi(sub_closes, period=14)

            # MACD
            if len(sub_closes) >= 35:
                macd_res = TechnicalIndicatorsEngine.calculate_macd(sub_closes)
                macd_list[i] = macd_res["macd"]
                macd_signal_list[i] = macd_res["signal"]
                macd_hist_list[i] = macd_res["histogram"]

            # Bollinger Bands
            if len(sub_closes) >= 20:
                bb_res = TechnicalIndicatorsEngine.calculate_bollinger_bands(sub_closes, period=20, num_std=2.0)
                bb_upper[i] = bb_res["upper"]
                bb_middle[i] = bb_res["middle"]
                bb_lower[i] = bb_res["lower"]

            # ATR
            if len(sub_closes) >= 15:
                atr_list[i] = TechnicalIndicatorsEngine.calculate_atr(sub_highs, sub_lows, sub_closes, period=14)

        df["rsi"] = rsi_list
        df["macd"] = macd_list
        df["macd_signal"] = macd_signal_list
        df["macd_hist"] = macd_hist_list
        df["bb_upper"] = bb_upper
        df["bb_middle"] = bb_middle
        df["bb_lower"] = bb_lower
        df["atr"] = atr_list

        return df

    def construct_empirical_option_panels(
        self,
        underlying_df: pd.DataFrame,
        vix_df: Optional[pd.DataFrame] = None,
        strike_step: float = 50.0,
        strikes_above_below: int = 5,
        risk_free_rate: float = 0.065,
        dividend_yield: float = 0.012,
    ) -> pd.DataFrame:
        """
        Constructs consistent cross-sectional option chain panels for each historical date.
        Uses authentic NSE Bhavcopy archives to extract real market settlement prices.
        """
        logger.info("Constructing option chain panel dataset from authentic NSE Bhavcopy...")
        records: List[Dict[str, Any]] = []

        downloader = NseBhavcopyDownloader()

        for _, row in underlying_df.iterrows():
            current_date = row["date"]
            spot = float(row["close"])
            if spot <= 0:
                continue

            atm_strike = round(spot / strike_step) * strike_step
            target_strikes = [
                atm_strike + (i * strike_step)
                for i in range(-strikes_above_below, strikes_above_below + 1)
            ]

            # Fetch authentic Bhavcopy for the date
            bhav_df = downloader.fetch_daily_fo_bhavcopy(current_date)
            if bhav_df is None or bhav_df.empty:
                logger.warning(f"Skipping {current_date} due to missing Bhavcopy (likely a holiday).")
                continue

            # Extract actual options
            raw_options = downloader.extract_nifty_options(bhav_df, spot, risk_free_rate)
            if not raw_options:
                logger.warning(f"No NIFTY options found in Bhavcopy for {current_date}.")
                continue

            # BUG FIX #1: Filter to NEAREST MONTHLY expiry only.
            # The Bhavcopy contains options across ALL expiries (weekly, monthly, quarterly, LEAPS).
            # Without this filter, a single strike may map to a 7-day or 1826-day contract
            # depending on which row is encountered first, causing phantom P&L in backtests.
            all_expiries = sorted(set(opt["expiry_date"] for opt in raw_options))
            # Select the nearest expiry that is >= 7 days out (skip weeklies expiring tomorrow)
            nearest_expiry = None
            for exp in all_expiries:
                dte = (exp - current_date).days
                if dte >= 7:
                    nearest_expiry = exp
                    break
            if nearest_expiry is None:
                nearest_expiry = all_expiries[0]  # Fallback to absolute nearest
            
            raw_options = [o for o in raw_options if o["expiry_date"] == nearest_expiry]

            # Filter options that match our target strikes grid
            calls_map = {}
            puts_map = {}
            for opt in raw_options:
                if opt["strike"] in target_strikes:
                    if opt["option_type"] == "call":
                        calls_map[opt["strike"]] = opt
                    else:
                        puts_map[opt["strike"]] = opt

            # We need valid IVs to build the volatility surface
            valid_strikes = []
            valid_ivs = []
            
            for k in target_strikes:
                # Build surface using Call IVs primarily, fallback to Put IVs
                if k in calls_map and calls_map[k].get("market_iv"):
                    valid_strikes.append(k)
                    valid_ivs.append(calls_map[k]["market_iv"])
                elif k in puts_map and puts_map[k].get("market_iv"):
                    valid_strikes.append(k)
                    valid_ivs.append(puts_map[k]["market_iv"])

            if len(valid_strikes) < 4:
                logger.warning(f"Not enough valid IVs to construct surface for {current_date}.")
                continue

            # Fit Volatility Surface using REAL MARKET IVs
            vol_surface = VolatilitySurface(strikes=valid_strikes, ivs=valid_ivs, spot=spot)

            # Construct final records
            for k in target_strikes:
                call_opt = calls_map.get(k)
                put_opt = puts_map.get(k)

                if not call_opt and not put_opt:
                    continue

                # We assume days to expiry is the same for the daily chain
                days_to_expiry = call_opt["days_to_expiry"] if call_opt else put_opt["days_to_expiry"]
                t_years = days_to_expiry / 365.0

                surface_iv = vol_surface.get_surface_iv(k)

                # Solve PDE fair price using smooth surface IV
                call_pde = vol_surface.compute_pde_fair_value(
                    strike=k, spot=spot, expiry_years=t_years, rate=risk_free_rate, option_type="call", grid_m=300, grid_n=300
                )
                put_pde = vol_surface.compute_pde_fair_value(
                    strike=k, spot=spot, expiry_years=t_years, rate=risk_free_rate, option_type="put", grid_m=300, grid_n=300
                )

                call_mkt = call_opt["settle_price"] if call_opt else 0.0
                put_mkt = put_opt["settle_price"] if put_opt else 0.0

                call_mispricing = round(call_mkt - call_pde, 4) if call_mkt > 0 else 0.0
                put_mispricing = round(put_mkt - put_pde, 4) if put_mkt > 0 else 0.0

                # Extract market IV, fallback to None
                call_iv = call_opt.get("market_iv") if call_opt else None
                put_iv = put_opt.get("market_iv") if put_opt else None
                market_iv = call_iv if call_iv else (put_iv if put_iv else None)

                if market_iv is None:
                    continue # Skip if both are completely illiquid

                records.append(
                    {
                        "date": current_date,
                        "spot": spot,
                        "strike": k,
                        "days_to_expiry": days_to_expiry,
                        "expiry_years": t_years,
                        "market_iv": market_iv,
                        "surface_iv": surface_iv,
                        "call_mkt_price": call_mkt,
                        "call_pde_price": call_pde,
                        "call_mispricing": call_mispricing,
                        "put_mkt_price": put_mkt,
                        "put_pde_price": put_pde,
                        "put_mispricing": put_mispricing,
                        "is_atm": (k == atm_strike),
                    }
                )

        options_df = pd.DataFrame(records)
        logger.info(f"Built options panel with {len(options_df)} total strike records")
        return options_df

    def build_and_save_all(self, days: int = 180) -> Dict[str, str]:
        """
        Run complete data pipeline and save to Parquet and CSV files.
        """
        ohlcv_raw = self.fetch_underlying_ohlcv("^NSEI", days=days + 50)
        vix_df = self.fetch_india_vix(days=days + 50)

        # Merge VIX with OHLCV
        ohlcv_enriched = self.enrich_with_technical_indicators(ohlcv_raw)
        if not vix_df.empty:
            ohlcv_enriched = pd.merge(ohlcv_enriched, vix_df, on="date", how="left")
            ohlcv_enriched["vix_close"] = ohlcv_enriched["vix_close"].bfill().ffill()

        # Trim to target days
        ohlcv_final = ohlcv_enriched.tail(days).reset_index(drop=True)

        options_df = self.construct_empirical_option_panels(
            underlying_df=ohlcv_final, vix_df=vix_df
        )

        # Save files
        ohlcv_csv = os.path.join(self.output_dir, "nifty_daily_ohlcv.csv")
        ohlcv_parquet = os.path.join(self.output_dir, "nifty_daily_ohlcv.parquet")
        options_csv = os.path.join(self.output_dir, "nifty_option_chains.csv")
        options_parquet = os.path.join(self.output_dir, "nifty_option_chains.parquet")

        ohlcv_final.to_csv(ohlcv_csv, index=False)
        ohlcv_final.to_parquet(ohlcv_parquet, index=False)
        options_df.to_csv(options_csv, index=False)
        options_df.to_parquet(options_parquet, index=False)

        logger.info(f"[OK] Saved datasets to {self.output_dir}")
        return {
            "ohlcv_csv": ohlcv_csv,
            "ohlcv_parquet": ohlcv_parquet,
            "options_csv": options_csv,
            "options_parquet": options_parquet,
        }


if __name__ == "__main__":
    collector = HistoricalDataCollector()
    collector.build_and_save_all(days=180)
