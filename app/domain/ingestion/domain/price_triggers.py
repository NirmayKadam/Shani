# app/domain/ingestion/price_triggers.py — Price-based sentiment triggers
#
# Detects significant price movements that should influence sentiment analysis.
# Computed in the Ingestion domain (which owns price data) and published as
# events for the Sentiment domain to incorporate.

import json
import logging
from typing import Optional

from app.shared.constants import PriceTriggerType, RedisKeys, TTL

Logger = logging.getLogger(__name__)

# ── Thresholds ──────────────────────────────────────────────────

FLASH_MOVE_THRESHOLD = 1.5      # ±1.5% in a single poll cycle
VOLUME_ANOMALY_MULTIPLIER = 3.0  # 3× rolling average


class PriceTriggerDetector:
    """
    Compares the latest price against the previously cached price
    to detect significant movements.

    Usage:
        detector = PriceTriggerDetector(redis_client)
        triggers = await detector.check("NIFTY", current_price=22500.0, current_volume=500000)
    """

    def __init__(self, redis_client) -> None:
        self._Redis = redis_client

    async def check(
        self,
        symbol: str,
        current_price: float,
        current_volume: int = 0,
    ) -> list[dict]:
        """
        Check for price-based triggers by comparing against cached previous price.

        Returns list of trigger event dicts (may be empty).
        """
        triggers: list[dict] = []
        cache_key = f"trigger:prev_price:{symbol.upper()}"

        # Get previous price from Redis
        prev_data_str = await self._Redis.get(cache_key)

        if prev_data_str:
            prev_data = json.loads(prev_data_str)
            prev_price = float(prev_data.get("price", current_price))
            prev_volume = int(prev_data.get("volume", 0))

            if prev_price > 0:
                change_pct = ((current_price - prev_price) / prev_price) * 100

                # Flash Drop
                if change_pct <= -FLASH_MOVE_THRESHOLD:
                    triggers.append({
                        "symbol": symbol.upper(),
                        "trigger_type": PriceTriggerType.FLASH_DROP.value,
                        "current_price": current_price,
                        "previous_price": prev_price,
                        "change_percent": round(change_pct, 2),
                        "description": f"{symbol} dropped {abs(change_pct):.2f}% "
                                       f"(₹{prev_price:,.2f} → ₹{current_price:,.2f})",
                    })
                    Logger.warning("⚠️ FLASH DROP: %s — %.2f%%", symbol, change_pct)

                # Spike Up
                elif change_pct >= FLASH_MOVE_THRESHOLD:
                    triggers.append({
                        "symbol": symbol.upper(),
                        "trigger_type": PriceTriggerType.SPIKE_UP.value,
                        "current_price": current_price,
                        "previous_price": prev_price,
                        "change_percent": round(change_pct, 2),
                        "description": f"{symbol} spiked {change_pct:.2f}% "
                                       f"(₹{prev_price:,.2f} → ₹{current_price:,.2f})",
                    })
                    Logger.warning("🚀 SPIKE UP: %s — +%.2f%%", symbol, change_pct)

            # Volume Anomaly (compare against rolling average)
            if current_volume > 0 and prev_volume > 0:
                vol_avg_key = f"trigger:vol_avg:{symbol.upper()}"
                vol_avg_str = await self._Redis.get(vol_avg_key)

                if vol_avg_str:
                    vol_avg = float(vol_avg_str)
                    if vol_avg > 0 and current_volume > vol_avg * VOLUME_ANOMALY_MULTIPLIER:
                        triggers.append({
                            "symbol": symbol.upper(),
                            "trigger_type": PriceTriggerType.VOLUME_ANOMALY.value,
                            "current_price": current_price,
                            "previous_price": prev_price,
                            "change_percent": round(current_volume / vol_avg, 2),
                            "description": f"{symbol} volume {current_volume:,} is "
                                           f"{current_volume/vol_avg:.1f}× rolling average",
                        })
                        Logger.warning("📊 VOLUME ANOMALY: %s — %d vs avg %d",
                                       symbol, current_volume, int(vol_avg))

                    # Update rolling average (exponential smoothing α=0.2)
                    new_avg = 0.8 * vol_avg + 0.2 * current_volume
                    await self._Redis.set(vol_avg_key, str(round(new_avg, 2)), ex=86400)
                else:
                    # Seed the rolling average
                    await self._Redis.set(vol_avg_key, str(float(current_volume)), ex=86400)

        # Cache current price for next comparison
        cache_data = json.dumps({"price": current_price, "volume": current_volume})
        await self._Redis.set(cache_key, cache_data, ex=TTL.MARKET_PRICE)

        return triggers
