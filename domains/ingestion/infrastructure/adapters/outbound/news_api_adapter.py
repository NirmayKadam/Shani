"""
File Overview: Outbound adapter for NewsAPI. Provides lightweight async headline fetching and mapping.

All Functions/Classes:
- NewsFetcher: Core async HTTP client for NewsAPI. Take search queries and send raw article lists.
- fetch: Execute multi-query fallback logic. Take symbol and send list of headline dictionaries.
- news_api_adapter: Port implementation for news source. Take symbol and send raw_article_dto list.

Endpoints/APIs: NewsAPI (v2/everything)

Database Tables: None
"""

import logging
from typing import Optional, List

from domains.ingestion.application.ports.interface.outbound.i_news_source import i_news_source
from domains.ingestion.application.dto.raw_article_dto import raw_article_dto

import aiohttp

logger = logging.getLogger(__name__)

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

    async def close(self) -> None:
        pass

    async def fetch(self, symbol: str, max_results: int = _MAX_HEADLINES) -> list[dict]:
        """
        Fetch latest news headlines for a stock symbol from NewsAPI.
        Tries multiple query variations if initial search returns nothing.
        """
        if not self._ApiKey:
            logger.warning("NEWS_API_KEY not set — returning empty headlines for %s", symbol)
            return []

        # Strip common vendor suffixes for cleaner NewsAPI query
        search_symbol = symbol.upper()
        for suffix in [".NS", ".BO", ".NX"]:
            if search_symbol.endswith(suffix):
                search_symbol = search_symbol[: -len(suffix)]
                break

        # Define query variations from specific to broad
        queries = [
            f"{search_symbol} stock India",
            f"{search_symbol} stock",
            search_symbol
        ]

        # Special handling for well-known Indian stocks to avoid noise if needed
        # but here we prioritize finding *anything* for specific symbols like CASTROLIND
        
        data = {"articles": []}
        final_query = ""

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            for q in queries:
                params = {
                    "q": q,
                    "apiKey": self._ApiKey,
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": min(max_results, 100),
                }

                try:
                    async with session.get(_NEWS_API_BASE, params=params) as resp:
                        if resp.status != 200:
                            body = await resp.text()
                            logger.error("[%s] NewsAPI returned %d for query '%s': %s", 
                                         symbol, resp.status, q, body[:200])
                            continue

                        data = await resp.json()
                        if data.get("totalResults", 0) > 0:
                            final_query = q
                            break
                        else:
                            logger.info("[%s] No results for query: '%s'", symbol, q)

                except (aiohttp.ClientError, Exception) as exc:
                    logger.error("[%s] NewsAPI request error for query '%s': %s", symbol, q, exc)
                    continue

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

        if headlines:
            logger.info("[%s] Fetched %d headlines from NewsAPI using query '%s'", 
                        symbol, len(headlines), final_query)
        else:
            logger.warning("[%s] No headlines found after trying all query variations", symbol)
            
        return headlines


class news_api_adapter(i_news_source):
    def __init__(self, api_key: str):
        self._fetcher = NewsFetcher(api_key=api_key)
        
    async def fetch_articles(self, symbol: str) -> List[raw_article_dto]:
        headlines = await self._fetcher.fetch(symbol)
        # map to DTO
        dtos = []
        for h in headlines:
            from datetime import datetime
            
            pub = h.get("published_at")
            if not pub:
                pub = datetime.now()
            elif isinstance(pub, str):
                try: pub = datetime.fromisoformat(pub.replace('Z', '+00:00'))
                except: pub = datetime.now()
                
            dtos.append(raw_article_dto(
                symbol=symbol,
                headline=h.get('headline', ''),
                body=h.get('content', ''),
                source=h.get('source_name', ''),
                published_at=pub,
                url=h.get('source_url', '')
            ))
        return dtos
