"""
File Overview: Application service for fusing news sentiment and ML predictions into composite market signals.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class SignalComposerService:
    """
    Fuses multiple analytical sources into a unified market signal.
    """

    def compose_signal(
        self, 
        symbol: str, 
        sentiment_agg: Dict[str, Any], 
        prediction: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Fuse sentiment data and ML prediction.
        
        sentiment_agg: Result from TimeframeComputerService.compute_all
        prediction: Result from DailyPredictorService.generate_prediction
        """
        try:
            # Use daily sentiment for primary signal
            daily_sent = sentiment_agg.get("daily", {})
            avg_score = daily_sent.get("avg_score", 0.0)
            label = daily_sent.get("label", "NEUTRAL")
            
            pred_label = prediction.get("prediction", "NEUTRAL")
            pred_conf = prediction.get("confidence", 0.0)
            
            # Logic fusion
            composite_label = "NEUTRAL"
            strength = 0.0
            
            # Signal derivation
            if avg_score > 0.2: # Bullish sentiment
                if pred_label == "VOL_CRUSH":
                    composite_label = "STRONG_BULLISH"
                    strength = 0.8 + (0.2 * pred_conf)
                elif pred_label == "VOL_EXPAND":
                    composite_label = "VOLATILE_BULLISH"
                    strength = 0.6
                else:
                    composite_label = "BULLISH"
                    strength = 0.5
            elif avg_score < -0.2: # Bearish sentiment
                if pred_label == "VOL_CRUSH":
                    composite_label = "STRONG_BEARISH"
                    strength = 0.8 + (0.2 * pred_conf)
                elif pred_label == "VOL_EXPAND":
                    composite_label = "VOLATILE_BEARISH"
                    strength = 0.6
                else:
                    composite_label = "BEARISH"
                    strength = 0.5
            else: # Neutral sentiment
                if pred_label == "VOL_EXPAND":
                    composite_label = "VOL_BREAKOUT_WATCH"
                    strength = 0.4
                else:
                    composite_label = "NEUTRAL"
                    strength = 0.1

            return {
                "symbol": symbol.upper(),
                "composite_label": composite_label,
                "strength": round(strength, 2),
                "sentiment_avg": avg_score,
                "prediction": pred_label,
                "composed_at": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "daily_count": daily_sent.get("count", 0),
                    "pred_confidence": pred_conf
                }
            }
        except Exception as exc:
            logger.error("[%s] Signal composition failed: %s", symbol, exc)
            return {
                "symbol": symbol.upper(),
                "composite_label": "NEUTRAL",
                "strength": 0.0,
                "composed_at": datetime.now(timezone.utc).isoformat()
            }
