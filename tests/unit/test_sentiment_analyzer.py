"""
Unit tests for SentimentAnalyzerService.

Migrated from: scripts/test_service.py (AnalysisService renamed to SentimentAnalyzerService).
Tests compute_aggregate() and compute_pcr() — pure static methods.
"""

import pytest
from domains.analytics.application.services.nlp.analyzer_service import SentimentAnalyzerService


@pytest.mark.unit
class TestComputeAggregate:

    def test_bullish_aggregate(self):
        headlines = [
            {"sentiment_label": "BULLISH", "sentiment_score": 0.85},
            {"sentiment_label": "BULLISH", "sentiment_score": 0.72},
            {"sentiment_label": "NEUTRAL", "sentiment_score": 0.05},
        ]
        result = SentimentAnalyzerService.compute_aggregate(headlines)
        assert result["label"] == "BULLISH"
        assert result["count"] == 3
        assert result["bullish_pct"] == pytest.approx(66.7, abs=0.1)
        assert result["avg_score"] == pytest.approx(0.54, abs=0.01)

    def test_bearish_aggregate(self):
        headlines = [
            {"sentiment_label": "BEARISH", "sentiment_score": -0.80},
            {"sentiment_label": "BEARISH", "sentiment_score": -0.65},
            {"sentiment_label": "NEUTRAL", "sentiment_score": -0.05},
        ]
        result = SentimentAnalyzerService.compute_aggregate(headlines)
        assert result["label"] == "BEARISH"
        assert result["avg_score"] == pytest.approx(-0.50, abs=0.01)

    def test_neutral_aggregate(self):
        headlines = [
            {"sentiment_label": "BULLISH", "sentiment_score": 0.15},
            {"sentiment_label": "BEARISH", "sentiment_score": -0.12},
            {"sentiment_label": "NEUTRAL", "sentiment_score": 0.02},
        ]
        result = SentimentAnalyzerService.compute_aggregate(headlines)
        assert result["label"] == "NEUTRAL"

    def test_empty_headlines(self):
        result = SentimentAnalyzerService.compute_aggregate([])
        assert result["label"] == "NEUTRAL"
        assert result["count"] == 0

    def test_mixed_with_fixture(self, sample_scored_headlines):
        result = SentimentAnalyzerService.compute_aggregate(sample_scored_headlines)
        assert result["count"] == 5
        assert result["bullish_pct"] == 40.0
        assert result["bearish_pct"] == 40.0


@pytest.mark.unit
class TestComputePCR:

    def test_compute_pcr_valid(self, sample_parsed_chain):
        result = SentimentAnalyzerService.compute_pcr(sample_parsed_chain)
        assert result is not None
        assert result["ce_volume"] == 40000
        assert result["pe_volume"] == 35000
        assert result["pcr"] == pytest.approx(35000 / 40000, abs=0.0001)
        assert result["ce_oi"] == 170000
        assert result["pe_oi"] == 155000

    def test_compute_pcr_empty(self):
        assert SentimentAnalyzerService.compute_pcr({}) is None
        assert SentimentAnalyzerService.compute_pcr(None) is None
        assert SentimentAnalyzerService.compute_pcr({"chains": {}}) is None

    def test_compute_pcr_zero_ce_volume(self):
        chain = {"chains": {"2026-05-29": [
            {"strike": 24500.0, "type": "PE", "volume": 1000, "oi": 500},
        ]}}
        result = SentimentAnalyzerService.compute_pcr(chain)
        assert result["pcr"] == 0.0
        assert result["pe_volume"] == 1000
