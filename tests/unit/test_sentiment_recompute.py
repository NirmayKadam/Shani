"""
Unit tests for recompute_and_publish_aggregates.

Migrated from: scripts/test_recompute.py
Uses mocked dependencies instead of live Redis/Postgres.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from domains.analytics.application.services.nlp.sentiment_orchestrator_service import (
    recompute_and_publish_aggregates,
    SubscriberDependencies,
)
from domains.analytics.domain.entities.sentiment_score_entity import SentimentScoreEntity


def _make_mock_deps(scores=None):
    """Create mocked SubscriberDependencies with optional score data."""
    deps = MagicMock(spec=SubscriberDependencies)
    deps.store = AsyncMock()
    deps.store.get_last_n = AsyncMock(return_value=scores or [])
    deps.cache = AsyncMock()
    deps.publisher = AsyncMock()
    deps.timeframe_computer = MagicMock()
    deps.timeframe_computer.compute_all = MagicMock(return_value={
        "1h": {"label": "BULLISH", "avg_score": 0.5, "count": 10},
        "4h": {"label": "NEUTRAL", "avg_score": 0.05, "count": 25},
        "1d": {"label": "BEARISH", "avg_score": -0.3, "count": 50},
    })
    deps.scorer = AsyncMock()
    deps.predictor = AsyncMock()
    deps.composer = MagicMock()
    return deps


def _make_score_entities(n=5):
    """Generate sample SentimentScoreEntity objects."""
    return [
        SentimentScoreEntity(symbol="NIFTY", label="BULLISH", score=0.7, confidence=0.9),
        SentimentScoreEntity(symbol="NIFTY", label="BEARISH", score=-0.5, confidence=0.85),
        SentimentScoreEntity(symbol="NIFTY", label="NEUTRAL", score=0.02, confidence=0.7),
        SentimentScoreEntity(symbol="NIFTY", label="BULLISH", score=0.6, confidence=0.88),
        SentimentScoreEntity(symbol="NIFTY", label="BEARISH", score=-0.8, confidence=0.92),
    ][:n]


@pytest.mark.unit
class TestRecomputeAndPublishAggregates:

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_scores(self):
        deps = _make_mock_deps(scores=[])
        result = await recompute_and_publish_aggregates("NIFTY", deps)
        assert result == {}
        deps.publisher.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_timeframe_data(self):
        scores = _make_score_entities(5)
        deps = _make_mock_deps(scores=scores)

        result = await recompute_and_publish_aggregates("NIFTY", deps)

        assert "1h" in result
        assert "4h" in result
        assert "1d" in result
        assert result["1h"]["label"] == "BULLISH"

    @pytest.mark.asyncio
    async def test_publishes_aggregates(self):
        scores = _make_score_entities(3)
        deps = _make_mock_deps(scores=scores)

        await recompute_and_publish_aggregates("NIFTY", deps)

        # Should publish one event per timeframe
        assert deps.publisher.publish.call_count == 3

    @pytest.mark.asyncio
    async def test_calls_store_get_last_n(self):
        deps = _make_mock_deps(scores=_make_score_entities(2))

        await recompute_and_publish_aggregates("NIFTY", deps)

        deps.store.get_last_n.assert_awaited_once_with("NIFTY", 1000)

    @pytest.mark.asyncio
    async def test_calls_timeframe_computer(self):
        scores = _make_score_entities(3)
        deps = _make_mock_deps(scores=scores)

        await recompute_and_publish_aggregates("NIFTY", deps)

        deps.timeframe_computer.compute_all.assert_called_once()
        call_args = deps.timeframe_computer.compute_all.call_args[0][0]
        assert len(call_args) == 3
        assert all("sentiment_label" in h for h in call_args)
        assert all("sentiment_score" in h for h in call_args)
