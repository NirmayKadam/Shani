from datetime import datetime, timezone

import pytest

from shared.utils.market_time import nearest_expiry, parse_expiry, risk_free_rate_for, years_to_expiry


@pytest.mark.unit
class TestYearsToExpiry:
    def test_counts_to_1530_ist_settlement(self):
        # 2026-06-04 04:00 UTC -> settlement 2026-06-05 10:00 UTC = 30 hours.
        now = datetime(2026, 6, 4, 4, 0, tzinfo=timezone.utc)
        assert years_to_expiry("2026-06-05", now) == pytest.approx(30 / (365 * 24))

    def test_expiry_day_afternoon_is_floored_positive(self):
        after_settlement = datetime(2026, 6, 5, 11, 0, tzinfo=timezone.utc)
        assert 0 < years_to_expiry("2026-06-05", after_settlement) < 1e-5

    def test_unparseable_expiry(self):
        assert years_to_expiry("05-Jun-2026") is None
        assert parse_expiry("") is None


@pytest.mark.unit
def test_nearest_expiry_skips_settled_and_bad_dates():
    now = datetime(2026, 6, 5, 11, 0, tzinfo=timezone.utc)  # after 2026-06-05 settlement
    assert nearest_expiry(["2026-06-12", "2026-06-05", "bad", "2026-06-19"], now) == "2026-06-12"
    assert nearest_expiry([], now) is None


@pytest.mark.unit
def test_risk_free_rate_by_market():
    assert risk_free_rate_for("NIFTY") == pytest.approx(0.065)
    assert risk_free_rate_for("RELIANCE.NS") == pytest.approx(0.065)
    assert risk_free_rate_for("AAPL") == pytest.approx(0.0525)
