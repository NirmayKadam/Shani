"""
File Overview: Factory function to return the configured market price / option chain adapter.
"""

import logging
from app.config import get_settings

logger = logging.getLogger(__name__)


def get_market_data_adapter():
    """
    Returns the outbound adapter according to MARKET_DATA_PROVIDER configuration.
    """
    settings = get_settings()
    provider = settings.MarketDataProvider.strip().lower()

    if provider == "groww":
        from domains.ingestion.infrastructure.adapters.outbound.groww_api_adapter import GrowwApiAdapter
        logger.info("Initializing GrowwApiAdapter as the market data provider.")
        return GrowwApiAdapter(
            api_key=settings.GrowwApiKey,
            secret_key=settings.GrowwApiSecret,
            access_token=settings.GrowwAccessToken
        )
    else:
        from domains.ingestion.infrastructure.adapters.outbound.nse_api_adapter import NseApiAdapter
        logger.info("Initializing NseApiAdapter (yfinance/NSE proxy) as the market data provider.")
        return NseApiAdapter()
