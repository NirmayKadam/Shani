# app/domain/sentiment/timeframes.py — Multi-timeframe sentiment aggregation
#
# Computes sentiment aggregates across 4 time windows:
#   Intraday (6h), Daily (24h), Weekly (7d), Monthly (30d)

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from shared.constants import Timeframe

logger = logging.getLogger(__name__)

# Timeframe window definitions
_WINDOWS = {
    Timeframe.INTRADAY: timedelta(hours=6),
    Timeframe.DAILY:    timedelta(hours=24),
    Timeframe.WEEKLY:   timedelta(days=7),
    Timeframe.MONTHLY:  timedelta(days=30),
}


class TimeframeComputer:
    """
    Computes multi-timeframe sentiment aggregates from a list of
    timestamped scored headlines.

    Usage:
        computer = TimeframeComputer()
        result = computer.compute_all(scored_headlines)
        # Returns: {"intraday": {...}, "daily": {...}, "weekly": {...}, "monthly": {...}}
    """

    def compute_all(self, scored_headlines: list[dict]) -> dict[str, dict]:
        """
        Compute aggregates for all timeframes.

        Input: List of scored headline dicts with 'published_at' and 'sentiment_score'.
        Output: Dict mapping timeframe name to aggregate dict.
        """
        now = datetime.now(timezone.utc)
        result: dict[str, dict] = {}

        for tf, window in _WINDOWS.items():
            cutoff = now - window
            filtered = self._filter_by_time(scored_headlines, cutoff)
            aggregate = self._compute_aggregate(filtered)
            aggregate["timeframe"] = tf.value
            result[tf.value] = aggregate

        # Compute trend for each timeframe by comparing with the previous window
        for tf in _WINDOWS:
            current = result[tf.value]
            prev_window = _WINDOWS[tf] * 2  # Double the window for "previous" period
            prev_cutoff_start = now - prev_window
            prev_cutoff_end = now - _WINDOWS[tf]

            prev_filtered = self._filter_by_time_range(
                scored_headlines, prev_cutoff_start, prev_cutoff_end
            )
            prev_agg = self._compute_aggregate(prev_filtered)

            current["trend"] = self._compute_trend(
                current["avg_score"], prev_agg["avg_score"]
            )

        return result

    @staticmethod
    def _filter_by_time(headlines: list[dict], cutoff: datetime) -> list[dict]:
        """Filter headlines to those published after the cutoff."""
        result = []
        for h in headlines:
            pub_str = h.get("published_at", "")
            if not pub_str:
                continue
            try:
                pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                if pub_dt >= cutoff:
                    result.append(h)
            except (ValueError, TypeError):
                # If we can't parse the date, include it anyway (conservative)
                result.append(h)
        return result

    @staticmethod
    def _filter_by_time_range(
        headlines: list[dict], start: datetime, end: datetime
    ) -> list[dict]:
        """Filter headlines to those published between start and end."""
        result = []
        for h in headlines:
            pub_str = h.get("published_at", "")
            if not pub_str:
                continue
            try:
                pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                if start <= pub_dt < end:
                    result.append(h)
            except (ValueError, TypeError):
                continue
        return result

    @staticmethod
    def _compute_aggregate(headlines: list[dict]) -> dict:
        """Compute basic aggregate from a filtered set of headlines."""
        if not headlines:
            return {
                "label": "NEUTRAL",
                "avg_score": 0.0,
                "bullish_pct": 0.0,
                "bearish_pct": 0.0,
                "neutral_pct": 0.0,
                "count": 0,
            }

        total = len(headlines)
        scores = [h.get("sentiment_score", 0.0) for h in headlines]
        avg = sum(scores) / total

        bullish = sum(1 for h in headlines if h.get("sentiment_label") == "BULLISH")
        bearish = sum(1 for h in headlines if h.get("sentiment_label") == "BEARISH")
        neutral = total - bullish - bearish

        if avg > 0.1:
            label = "BULLISH"
        elif avg < -0.1:
            label = "BEARISH"
        else:
            label = "NEUTRAL"

        return {
            "label": label,
            "avg_score": round(avg, 4),
            "bullish_pct": round((bullish / total) * 100, 1),
            "bearish_pct": round((bearish / total) * 100, 1),
            "neutral_pct": round((neutral / total) * 100, 1),
            "count": total,
        }

    @staticmethod
    def _compute_trend(current_score: float, previous_score: float) -> str:
        """Determine trend direction by comparing current vs previous period."""
        diff = current_score - previous_score
        if diff > 0.05:
            return "IMPROVING"
        elif diff < -0.05:
            return "DETERIORATING"
        else:
            return "STABLE"
