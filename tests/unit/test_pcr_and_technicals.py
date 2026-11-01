import pytest

from domains.analytics.application.dto.read_models_dto import compute_pcr
from domains.analytics.application.technicals_calculator import compute_all_technicals
from domains.analytics.api.pricer_router_api import _SYMBOL_PATTERN, _atm_call, _iv_percent


def _tick(strike, opt_type, oi, volume):
    return {"strike": strike, "type": opt_type, "oi": oi, "volume": volume}


@pytest.mark.unit
class TestComputePcr:
    def test_oi_ratio_of_nearest_expiry_only(self):
        chain = {"chains": {
            "2099-01-28": [_tick(100, "CE", 1000, 10), _tick(100, "PE", 1500, 30)],
            "2099-02-25": [_tick(100, "CE", 1, 1), _tick(100, "PE", 99999, 99999)],
        }}
        result = compute_pcr(chain)
        assert result["expiry"] == "2099-01-28"
        assert result["pcr"] == 1.5           # put OI / call OI
        assert result["volume_pcr"] == 3.0    # put volume / call volume
        assert result["ce_oi"] == 1000 and result["pe_oi"] == 1500

    def test_no_call_side_means_no_data_not_zero(self):
        result = compute_pcr({"chains": {"2099-01-28": [_tick(100, "PE", 500, 5)]}})
        assert result["pcr"] is None
        assert result["volume_pcr"] is None

    def test_empty_chain(self):
        result = compute_pcr({})
        assert result["pcr"] is None and result["expiry"] is None


@pytest.mark.unit
class TestTechnicalsWithOhlc:
    closes = [100.0 + i for i in range(30)]
    highs = [c + 2.0 for c in closes]
    lows = [c - 3.0 for c in closes]

    def test_atr_uses_true_range(self):
        result = compute_all_technicals(self.closes[-1], self.closes, self.highs, self.lows)
        # True range = high - low = 5 every day (gaps are smaller), so ATR is 5
        assert result["atr"] == pytest.approx(5.0)

    def test_pivots_use_previous_session(self):
        result = compute_all_technicals(self.closes[-1], self.closes, self.highs, self.lows)
        h, l, c = self.highs[-2], self.lows[-2], self.closes[-2]
        assert result["pivots"]["p"] == pytest.approx(round((h + l + c) / 3, 2))

    def test_falls_back_without_ohlc(self):
        result = compute_all_technicals(self.closes[-1], self.closes)
        assert result["atr"] == pytest.approx(1.0)  # close-to-close moves of 1


@pytest.mark.unit
class TestPricerHelpers:
    def test_symbol_pattern_accepts_real_tickers(self):
        for symbol in ("NIFTY", "RELIANCE.NS", "^NSEI", "M&M", "BRK-B"):
            assert _SYMBOL_PATTERN.match(symbol)
        for symbol in ("$$$INVALID!!!", "NIFTY;DROP", ""):
            assert not _SYMBOL_PATTERN.match(symbol)

    def test_atm_is_chosen_from_calls_only(self):
        rows = [
            {"strike": 24000.0, "type": "PE"},   # nearest overall, but a put
            {"strike": 24100.0, "type": "CE"},
            {"strike": 23800.0, "type": "CE"},
        ]
        assert _atm_call(rows, 24010.0)["strike"] == 24100.0
        assert _atm_call([{"strike": 1.0, "type": "PE"}], 1.0) is None

    def test_iv_reported_in_percent(self):
        assert _iv_percent(0.142) == pytest.approx(14.2)
        assert _iv_percent(None) == 0.0
        assert _iv_percent(0) == 0.0
