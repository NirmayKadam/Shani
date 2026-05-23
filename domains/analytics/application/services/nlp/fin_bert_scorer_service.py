"""
File Overview: Application service for scoring headlines using FinBERT.
Wraps the low-level FinBertEngineService to provide domain-aligned scoring logic.
"""

import logging
from typing import List, Dict, Any
from domains.analytics.application.services.nlp.finbert_engine_service import FinBertEngineService

logger = logging.getLogger(__name__)

class FinBertScorerService:
    """
    Application service that uses FinBERT to score market headlines.
    """

    def __init__(self):
        self._engine = FinBertEngineService.get_instance()

    async def score_headlines(self, headlines: List[str]) -> List[Dict[str, Any]]:
        """
        Score a list of headlines and return structured sentiment data.
        
        Output format:
        [
            {
                "label": "BULLISH" | "BEARISH" | "NEUTRAL",
                "score": float (-1.0 to 1.0 adjusted),
                "confidence": float (0.0 to 1.0)
            },
            ...
        ]
        """
        if not headlines:
            return []

        try:
            raw_results = await self._engine.score_batch(headlines)
            
            processed = []
            for res in raw_results:
                # Adjust score based on label for numeric range [-1, 1]
                label = res["label"]
                conf = res["confidence"]
                
                if label == "BULLISH":
                    score = conf
                elif label == "BEARISH":
                    score = -conf
                else:
                    score = 0.0
                
                processed.append({
                    "label": label,
                    "score": score,
                    "confidence": conf
                })
                
            return processed
        except Exception as exc:
            logger.error("Failed to score headlines: %s", exc)
            return [{"label": "NEUTRAL", "score": 0.0, "confidence": 0.0} for _ in headlines]
