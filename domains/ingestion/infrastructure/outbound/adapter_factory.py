"""
File Overview: Factory function to return the configured market price / option chain adapter.
"""

import asyncio
import logging
import weakref
from app.config import get_settings

logger = logging.getLogger(__name__)

# One adapter per event loop: its aiohttp session, NSE cookies and Groww token are reused across
# polls instead of being rebuilt every 5-15 s. Sessions are bound to a loop, hence per loop.
_ADAPTERS: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, object]" = weakref.WeakKeyDictionary()


def get_market_data_adapter(redis_client=None):
    """
    Returns the outbound adapter according to MARKET_DATA_PROVIDER configuration.
    Accepts optional redis_client for adapters that support caching (e.g. dividend yield).
    The adapter is shared per event loop; callers must not close it.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return _build_adapter(redis_client)

    adapter = _ADAPTERS.get(loop)
    if adapter is None:
        adapter = _build_adapter(redis_client)
        _ADAPTERS[loop] = adapter
    elif redis_client is not None and getattr(adapter, "_redis", redis_client) is None:
        adapter._redis = redis_client
    return adapter


def _build_adapter(redis_client=None):
    settings = get_settings()
    provider = settings.MarketDataProvider.strip().lower()

    if provider == "groww":
        from domains.ingestion.infrastructure.outbound.groww_api_adapter import GrowwApiAdapter
        logger.info("Initializing GrowwApiAdapter as the market data provider.")
        return GrowwApiAdapter(
            api_key=settings.GrowwApiKey,
            secret_key=settings.GrowwApiSecret,
            access_token=settings.GrowwAccessToken,
            totp_secret=settings.GrowwTotpSecret,
            pin=settings.GrowwPin,
            redis_client=redis_client,
        )
    else:
        from domains.ingestion.infrastructure.outbound.nse_api_adapter import NseApiAdapter
        logger.info("Initializing NseApiAdapter (yfinance/NSE proxy) as the market data provider.")
        return NseApiAdapter()
