"""
File Overview: Core sentiment analysis engine that enriches headlines with FinBERT scores and calculates aggregate metrics.

All Functions/Classes:
- SentimentAnalyzer (class): Stateless logic for batch scoring and statistical summaries. Data: Raw Headlines -> Scored JSON.
- score_headlines: Performs NLP inference on batches. Data: Headlines list -> Scored list.
- compute_aggregate: Calculates mean and distribution stats. Data: Scored items -> Summary dict.
- compute_pcr: Calculates Put-Call Ratio from option data. Data: Option Chain -> PCR metrics.

Endpoints/APIs:
- None.

Database Tables:
- None.
"""
import json


import logging
from typing import Optional

from domains.analytics.application.services.nlp.finbert_engine_service import FinBertEngineService
from datetime import datetime, timezone

from shared.constants import SentimentLabel, RedisKeys, TTL

logger = logging.getLogger(__name__)


class SentimentAnalyzerService:
    """
    Stateless analyzer — scores headlines and computes aggregates.

    Usage:
        analyzer = SentimentAnalyzer()
        scored = await analyzer.score_headlines(headlines_list)
        aggregate = analyzer.compute_aggregate(scored_headlines_list)
    """

    def __init__(self, engine: Optional[FinBertEngineService] = None):
        self._Engine = engine

    async def score_headlines(self, headlines: list[dict]) -> list[dict]:
        """
        Score a batch of headlines with FinBERT.

        Input: [{"headline": str, "content": str, "source_name": str, "published_at": str}, ...]
        Output: Same dicts enriched with sentiment_label, sentiment_score, confidence
        """
        if not headlines:
            return []

        engine = self._Engine or FinBertEngineService.get_instance()

        # Combine headline + content for richer context, truncate to 512 chars
        texts = [
            f"{h.get('headline', '')} {h.get('content', '')}"[:512]
            for h in headlines
        ]

        results = await engine.score_batch(texts)

        scored: list[dict] = []
        for headline_dict, result in zip(headlines, results):
            label = result["label"]
            raw_score = result["score"]

            # Convert confidence to polarity: -1.0 to +1.0
            label_upper = label.upper()
            if label_upper in ["NEGATIVE", "BEARISH"]:
                polarity = -raw_score
            elif label_upper in ["NEUTRAL", "NONE"]:
                polarity = 0.0
            else:
                polarity = raw_score

            scored.append({
                **headline_dict,
                "sentiment_label": label,
                "sentiment_score": round(polarity, 4),
                "confidence": round(result["confidence"], 4),
            })

        logger.info("Scored %d headlines with FinBERT", len(scored))
        return scored

    @staticmethod
    def compute_aggregate(scored_headlines: list[dict]) -> dict:
        """
        Compute aggregate sentiment from a list of scored headlines.

        Returns:
            {
                "label": "BULLISH",
                "avg_score": 0.35,
                "bullish_pct": 60.0,
                "bearish_pct": 25.0,
                "neutral_pct": 15.0,
                "count": 20
            }
        """
        if not scored_headlines:
            return {
                "label": "NEUTRAL",
                "avg_score": 0.0,
                "bullish_pct": 0.0,
                "bearish_pct": 0.0,
                "neutral_pct": 0.0,
                "count": 0,
            }

        total = len(scored_headlines)
        scores = [h.get("sentiment_score", 0.0) for h in scored_headlines]
        avg_score = sum(scores) / total

        bullish = sum(1 for h in scored_headlines if h.get("sentiment_label") == "BULLISH")
        bearish = sum(1 for h in scored_headlines if h.get("sentiment_label") == "BEARISH")
        neutral = total - bullish - bearish

        # Determine overall label
        if avg_score > 0.1:
            label = "BULLISH"
        elif avg_score < -0.1:
            label = "BEARISH"
        else:
            label = "NEUTRAL"

        return {
            "label": label,
            "avg_score": round(avg_score, 4),
            "bullish_pct": round((bullish / total) * 100, 1),
            "bearish_pct": round((bearish / total) * 100, 1),
            "neutral_pct": round((neutral / total) * 100, 1),
            "count": total,
        }

    @staticmethod
    def compute_pcr(option_chain: dict) -> Optional[dict]:
        """
        Compute Put-Call Ratio from option chain data.

        Input: The full option chain dict from OptionChainFetcher.
        Output: {"pcr": float, "ce_volume": int, "pe_volume": int, ...}
        """
        if not option_chain or not option_chain.get("chains"):
            return None

        total_ce_vol = 0
        total_pe_vol = 0
        total_ce_oi = 0
        total_pe_oi = 0

        # Aggregate across all expiries
        for expiry, ticks in option_chain["chains"].items():
            for tick in ticks:
                vol = tick.get("volume", 0)
                oi = tick.get("oi", 0)
                if tick["type"] == "CE":
                    total_ce_vol += vol
                    total_ce_oi += oi
                elif tick["type"] == "PE":
                    total_pe_vol += vol
                    total_pe_oi += oi

        pcr = round(total_pe_vol / total_ce_vol, 4) if total_ce_vol > 0 else 0.0

        return {
            "pcr": pcr,
            "ce_volume": total_ce_vol,
            "pe_volume": total_pe_vol,
            "ce_oi": total_ce_oi,
            "pe_oi": total_pe_oi,
        }
