"""
File Overview: Authentic NSE Historical Derivatives Bhavcopy Downloader & Parser.
Fetches official National Stock Exchange (NSE) derivatives settlement archives,
extracts NIFTY index option chains (OPTIDX), and derives true market implied volatilities.
"""

import os
import sys
import io
import zipfile
import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
import requests

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from domains.analytics.domain.services.bsm_calculator import BsmCalculatorDomainService

logger = logging.getLogger(__name__)

# Standard NSE Request Headers to emulate browser session
NSE_ARCHIVE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com",
}


class NseBhavcopyDownloader:
    """
    Downloads and parses authentic NSE daily F&O Bhavcopy archives.
    """

    def __init__(self, cache_dir: Optional[str] = None) -> None:
        self.cache_dir = cache_dir or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "raw", "bhavcopy_cache")
        )
        os.makedirs(self.cache_dir, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update(NSE_ARCHIVE_HEADERS)

    def get_bhavcopy_url(self, target_date: date) -> str:
        """
        Generate NSE Derivatives Bhavcopy URL for a specific trading session.
        Standard format: https://nsearchives.nseindia.com/content/historical/DERIVATIVES/YYYY/MON/foDDMONYYYYbhav.csv.zip
        """
        year_str = target_date.strftime("%Y")
        mon_str = target_date.strftime("%b").upper()
        day_str = target_date.strftime("%d")
        return f"https://nsearchives.nseindia.com/content/historical/DERIVATIVES/{year_str}/{mon_str}/fo{day_str}{mon_str}{year_str}bhav.csv.zip"

    def fetch_daily_fo_bhavcopy(self, target_date: date) -> Optional[pd.DataFrame]:
        """
        Fetch and parse FO bhavcopy for a single date.
        """
        cache_filename = os.path.join(
            self.cache_dir, f"fo_{target_date.strftime('%Y%m%d')}.parquet"
        )
        if os.path.exists(cache_filename):
            try:
                return pd.read_parquet(cache_filename)
            except Exception as e:
                logger.warning(f"Failed reading cached bhavcopy for {target_date}: {e}")

        url = self.get_bhavcopy_url(target_date)
        try:
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200 and len(resp.content) > 1000:
                with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                    csv_name = z.namelist()[0]
                    with z.open(csv_name) as f:
                        df = pd.read_csv(f)
                        df.columns = [c.strip().upper() for c in df.columns]
                        df.to_parquet(cache_filename, index=False)
                        logger.info(f"Successfully downloaded and cached NSE Bhavcopy for {target_date}")
                        return df
            else:
                logger.debug(f"Bhavcopy not available for {target_date} (status {resp.status_code})")
                return None
        except Exception as ex:
            logger.debug(f"Network error fetching Bhavcopy for {target_date}: {ex}")
            return None

    def extract_nifty_options(
        self, bhav_df: pd.DataFrame, spot_price: float, risk_free_rate: float = 0.065
    ) -> List[Dict[str, Any]]:
        """
        Extract NIFTY index options and derive empirical implied volatility.
        """
        if bhav_df is None or bhav_df.empty:
            return []

        # Filter for NIFTY index options (OPTIDX)
        nifty_opts = bhav_df[
            (bhav_df.get("INSTRUMENT", "").str.strip() == "OPTIDX")
            & (bhav_df.get("SYMBOL", "").str.strip() == "NIFTY")
        ].copy()

        if nifty_opts.empty:
            return []

        records = []
        for _, row in nifty_opts.iterrows():
            try:
                strike = float(row["STRIKE_PR"])
                opt_type = "call" if row["OPTION_TYP"].strip() == "CE" else "put"
                close_price = float(row.get("CLOSE", row.get("SETTLE_PR", 0.0)))
                expiry_dt_raw = row["EXPIRY_DT"]
                
                # Parse expiry date
                expiry_date = pd.to_datetime(expiry_dt_raw).date()
                trade_date = pd.to_datetime(row["TIMESTAMP"]).date()
                days_to_expiry = max(1, (expiry_date - trade_date).days)
                t_years = days_to_expiry / 365.0

                # Compute implied volatility if option has active trading price
                iv = None
                if close_price > 0.5:
                    iv = BsmCalculatorDomainService.solve_implied_volatility(
                        market_price=close_price,
                        spot=spot_price,
                        strike=strike,
                        expiry_years=t_years,
                        rate=risk_free_rate,
                        option_type=opt_type,
                    )

                records.append(
                    {
                        "date": trade_date,
                        "strike": strike,
                        "option_type": opt_type,
                        "expiry_date": expiry_date,
                        "days_to_expiry": days_to_expiry,
                        "close_price": close_price,
                        "settle_price": float(row.get("SETTLE_PR", close_price)),
                        "open_interest": float(row.get("OPEN_INT", 0.0)),
                        "contracts_traded": float(row.get("CONTRACTS", 0.0)),
                        "market_iv": iv,
                    }
                )
            except Exception as e:
                continue

        return records
