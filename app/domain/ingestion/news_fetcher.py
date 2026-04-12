# app/domain/ingestion/news_fetcher.py — Lightweight NewsAPI client
#
# Pure fetch logic — no DB, no Redis, no dedup.
# Returns a list of headline dicts ready for FinBERT scoring.

import logging
from typing import Optional

import aiohttp

Logger = logging.getLogger(__name__)

_NEWS_API_BASE = "https://newsapi.org/v2/everything"
_MAX_HEADLINES = 20


class NewsFetcher:
    """
    Lightweight async news fetcher. Creates its own HTTP session.

    Usage:
        fetcher = NewsFetcher(api_key="...")
        headlines = await fetcher.fetch("NIFTY")
        await fetcher.close()
    """

    def __init__(self, api_key: str) -> None:
        self._ApiKey = api_key
        self._Session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._Session is None or self._Session.closed:
            self._Session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._Session

    async def close(self) -> None:
        if self._Session and not self._Session.closed:
            await self._Session.close()

    async def fetch(self, symbol: str, max_results: int = _MAX_HEADLINES) -> list[dict]:
        """
        Fetch latest news headlines for a stock symbol from NewsAPI.

        Returns a list of dicts:
            [{"headline": str, "content": str, "source_url": str,
              "source_name": str, "published_at": str}, ...]

        Returns empty list (never raises) if API key is missing or request fails.
        """
        if not self._ApiKey:
            Logger.warning("NEWS_API_KEY not set — returning empty headlines for %s", symbol)
            return []

        session = await self._ensure_session()

        params = {
            "q": f"{symbol} stock India",
            "apiKey": self._ApiKey,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": min(max_results, 100),
        }

        try:
            async with session.get(_NEWS_API_BASE, params=params) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    Logger.error(
                        "[%s] NewsAPI returned %d: %s", symbol, resp.status, body[:200]
                    )
                    return []

                data = await resp.json()

        except (aiohttp.ClientError, Exception) as exc:
            Logger.error("[%s] NewsAPI request error: %s", symbol, exc)
            return []

        headlines: list[dict] = []
        for item in data.get("articles", []):
            url = item.get("url", "")
            title = item.get("title", "")
            if not url or not title:
                continue

            headlines.append({
                "headline": title,
                "content": item.get("description", "") or "",
                "source_url": url,
                "source_name": (item.get("source") or {}).get("name", "Unknown"),
                "published_at": item.get("publishedAt", ""),
            })

            if len(headlines) >= max_results:
                break

        Logger.info("[%s] Fetched %d headlines from NewsAPI", symbol, len(headlines))
        return headlines
