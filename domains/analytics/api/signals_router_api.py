"""
File Overview: FastAPI router for signal-related analytics endpoints.

All Functions/Classes:
- get_signals: FastAPI GET endpoint. Take symbol from path and send placeholder response.

Endpoints/APIs:
- GET /v1/signals/{symbol}.

Database Tables:
- None.
"""
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException

from shared.utils.symbol_validator import SymbolValidator
from shared.infrastructure.redis_client import get_redis_client
from shared.constants import RedisKeys, Streams
from shared.infrastructure.event_bus.streams import DurableEventStream
from shared.infrastructure.event_bus.contracts import AnalysisRefreshRequestedV1
from domains.analytics.api.schemas import SignalResponse, SignalMetadata

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/signals", tags=["signals"])


def _generated_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def _error_envelope(*, error: str, code: str, details=None) -> dict:
    return {
        "generated_at": _generated_at(),
        "source": "frontend_api",
        "stale": True,
        "partial": True,
        "error": error,
        "code": code,
        "details": details,
    }


@router.get("/{symbol}", response_model=SignalResponse)
async def get_signals(symbol: str):
    """
    Get the composite market signal (news sentiment fused with ML prediction).
    Cache-first and decoupled.
    """
    symbol_upper = symbol.strip().upper()

    if not SymbolValidator.validate(symbol_upper):
        raise HTTPException(
            status_code=400,
            detail=_error_envelope(
                error=f"Symbol '{symbol_upper}' is invalid or not supported.",
                code="invalid_symbol",
                details={
                    "hint": "Ensure the ticker is correct (e.g., RELIANCE or AAPL). Use .NS suffix for Indian stocks if needed.",
                },
            ),
        )

    symbol_clean = SymbolValidator.get_clean_symbol(symbol_upper)
    redis = await get_redis_client()

    # Read composite signal from Redis
    signal_key = RedisKeys.SENTIMENT_SIGNAL.format(symbol=symbol_clean)
    cached = await redis.get(signal_key)

    if not cached:
        # Trigger background refresh
        try:
            stream_bus = DurableEventStream(redis)
            event = AnalysisRefreshRequestedV1(symbol=symbol_clean, reason="signal_api_cache_miss")
            await stream_bus.publish(Streams.ANALYSIS_REFRESH_REQUESTED, event.to_dict())
            logger.info("[%s] Triggered background refresh for signal cache miss", symbol_clean)
        except Exception as exc:
            logger.warning("[%s] Failed to publish background refresh request: %s", symbol_clean, exc)

        return SignalResponse(
            symbol=symbol_clean,
            composite_label="NEUTRAL",
            strength=0.0,
            sentiment_avg=0.0,
            prediction="NEUTRAL",
            composed_at=_generated_at(),
            metadata=SignalMetadata(daily_count=0, pred_confidence=0.0),
            generated_at=_generated_at(),
            source="redis_read_model",
            stale=True,
            partial=True,
            status="CALCULATING"
        )

    payload = json.loads(cached)
    composed_at_str = payload.get("composed_at", "")
    
    # Simple age check: stale if older than 10 minutes
    stale = True
    if composed_at_str:
        try:
            composed_at_dt = datetime.fromisoformat(composed_at_str.replace("Z", "+00:00"))
            age_seconds = (datetime.now(timezone.utc) - composed_at_dt).total_seconds()
            stale = age_seconds > 600  # 10 minutes
        except Exception:
            pass

    metadata_payload = payload.get("metadata", {})
    metadata = SignalMetadata(
        daily_count=metadata_payload.get("daily_count", 0),
        pred_confidence=metadata_payload.get("pred_confidence", 0.0)
    )

    return SignalResponse(
        symbol=symbol_clean,
        composite_label=payload.get("composite_label", "NEUTRAL"),
        strength=float(payload.get("strength", 0.0)),
        sentiment_avg=float(payload.get("sentiment_avg", 0.0)),
        prediction=payload.get("prediction", "NEUTRAL"),
        composed_at=composed_at_str,
        metadata=metadata,
        generated_at=_generated_at(),
        source="redis_read_model",
        stale=stale,
        partial=False,
        status="COMPLETED"
    )
