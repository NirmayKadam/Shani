"""
File Overview: Unit tests for On-Demand Multi-Day Historical Research Excel Exporter.
"""

from datetime import date
import io
from unittest.mock import MagicMock, patch
import pytest

openpyxl = pytest.importorskip("openpyxl")

from domains.analytics.application.historical_research_exporter import (
    MarketDataUnavailableError,
    fetch_historical_daily_prices,
    generate_strike_grid,
    generate_research_excel_workbook
)


def _test_prices(symbol: str, start: date, end: date):
    """Two trading days of made-up test prices (the test must not depend on yfinance)."""
    days = [date(2026, 8, 3), date(2026, 8, 4)]
    return {
        d: {"open": 180.0, "high": 182.0, "low": 178.5, "close": 180.0 + i, "volume": 1000,
            "history": [170.0 + j for j in range(30)]}
        for i, d in enumerate(days) if start <= d <= end
    }


def test_generate_strike_grid():
    # Test spot 24500 (Nifty level) -> step 100
    strikes = generate_strike_grid(24530.0, num_strikes_above_below=5)
    assert len(strikes) == 11
    assert 24500.0 in strikes
    assert strikes[0] == 24000.0
    assert strikes[-1] == 25000.0

    # Test spot 180 (IREDA level) -> step 2.5
    strikes_small = generate_strike_grid(180.0, num_strikes_above_below=3)
    assert len(strikes_small) == 7
    assert 180.0 in strikes_small


def test_missing_history_raises_instead_of_inventing_prices():
    empty = MagicMock()
    empty.history.return_value.empty = True
    with patch("yfinance.Ticker", return_value=empty):
        with pytest.raises(MarketDataUnavailableError):
            fetch_historical_daily_prices("IREDA.NS", date(2026, 8, 1), date(2026, 8, 5))


def test_generate_research_excel_workbook():
    start = date(2026, 8, 1)
    end = date(2026, 8, 5)
    with patch("domains.analytics.application.historical_research_exporter.fetch_historical_daily_prices",
               side_effect=_test_prices):
        excel_bytes = generate_research_excel_workbook("IREDA", start, end, layout_mode="separate_tabs")

    assert len(excel_bytes) > 0

    # Load bytes into openpyxl workbook
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    sheet_names = wb.sheetnames

    assert "Export Summary" in sheet_names
    # Check that sheets were generated for trading days
    assert len(sheet_names) >= 3

    ws_summary = wb["Export Summary"]
    assert ws_summary["A1"].value == "AlphaStreams — Historical Quantitative Options Research Export"
    assert ws_summary["B3"].value in ["IREDA", "IREDA.NS"]

    # Check daily chain sheet header formatting
    chain_sheets = [s for s in sheet_names if "Option Chain" in s]
    if chain_sheets:
        ws_chain = wb[chain_sheets[0]]
        assert ws_chain.cell(row=1, column=9).value == "STRIKE"
        assert ws_chain.cell(row=1, column=3).value == "CALLS - BS PRICE"
        assert ws_chain.cell(row=1, column=15).value == "PUTS - BS PRICE"
