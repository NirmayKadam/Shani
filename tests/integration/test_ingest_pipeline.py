import asyncio
import pytest
from unittest.mock import patch, MagicMock
from domains.ingestion.application.tasks.ingestion_tasks import _get_or_create_service
from domains.ingestion.application.dto.raw_article_dto import RawArticleDTO
from datetime import datetime, timezone


@pytest.mark.integration
async def test_news_ingestion_pipeline():
    """
    Automated test for triggering news ingestion without live external network requests.
    """
    svc = await _get_or_create_service()
    try:
        await svc._redis.ping()
    except Exception:
        pytest.skip("Redis server is not running")

    symbols = ["NIFTY", "RELIANCE"]
    
    # Prepare mock article data
    mock_articles = [
        RawArticleDTO(
            symbol="NIFTY",
            headline="Indian markets set for massive rally",
            body="Option chain volume surges as global sentiment shifts positive.",
            source="Reuters",
            published_at=datetime.now(timezone.utc),
            url="https://example.com/market-rally-2026"
        )
    ]

    with patch("domains.ingestion.infrastructure.adapters.outbound.news_api_adapter.NewsApiAdapter.fetch_articles", return_value=mock_articles):
        print("\n[+] Triggering news ingestion pipeline...")
        for symbol in symbols:
            try:
                await svc.ingest_news(symbol)
                print(f"  ✅ Ingestion dispatched for {symbol}")
            except Exception as e:
                assert False, f"Failed ingestion for {symbol}: {e}"
