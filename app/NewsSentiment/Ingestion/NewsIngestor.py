"""
NewsIngestor — fetches news articles, persists them, and dispatches sentiment analysis.

Self-contained: brings up its own asyncpg pool, aiohttp session, and Redis
connection so it can run independently of the (currently stub) infrastructure
clients.  When those are fleshed out, swap the helpers below for the shared
singletons.

Env vars consumed (all from .env):
    DATABASE_URL, REDIS_URL, NEWS_API_KEY,
    WATCHLIST_SYMBOLS, NEWS_POLL_INTERVAL_SECONDS
"""

import os
import logging
import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, field, asdict

import asyncpg
import aiohttp
import redis.asyncio as aioredis

# ── Logging ─────────────────────────────────────────────────────
Logger = logging.getLogger(__name__)
Logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))


# ── Domain Model ────────────────────────────────────────────────

@dataclass
class NewsArticle:
    """Mirrors the SentimentScores table columns that originate from news."""
    Symbol: str
    Headline: str
    Content: str
    SourceUrl: str
    SourceType: str = "NEWS"                 # NEWS | REDDIT | TELEGRAM | SEBI
    PublishedAt: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # ── helpers ──
    @property
    def UrlHash(self) -> str:
        """Deterministic dedup key for a URL."""
        return hashlib.sha256(self.SourceUrl.encode()).hexdigest()

    def ToDict(self) -> dict:
        return asdict(self)


# ── Configuration ───────────────────────────────────────────────

_DATABASE_URL: str = os.getenv(
    "DATABASE_URL", "postgresql://localhost:5432/postgres"
)
_REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
_NEWS_API_KEY: str = os.getenv("NEWS_API_KEY", "")
_NEWS_API_BASE: str = "https://newsapi.org/v2/everything"
_POLL_INTERVAL: int = int(os.getenv("NEWS_POLL_INTERVAL_SECONDS", "120"))
_WATCHLIST: list[str] = [
    s.strip()
    for s in os.getenv("WATCHLIST_SYMBOLS", "RELIANCE,INFY,TCS").split(",")
    if s.strip()
]
_DEDUP_TTL: int = 86_400  # 24 h — how long we remember a URL in Redis


# ── NewsIngestor ────────────────────────────────────────────────

class NewsIngestor:
    """
    Lifecycle:
        Ingestor = NewsIngestor()
        await Ingestor.Initialise()
        await Ingestor.IngestForSymbol("RELIANCE")   # one-shot
        await Ingestor.RunForever()                   # or poll loop
        await Ingestor.Shutdown()
    """

    def __init__(self) -> None:
        self._DbPool: Optional[asyncpg.Pool] = None
        self._Redis: Optional[aioredis.Redis] = None
        self._HttpSession: Optional[aiohttp.ClientSession] = None

    # ── Lifecycle ───────────────────────────────────────────────

    async def Initialise(self) -> None:
        """Spin up DB pool, Redis connection, and HTTP session."""
        Logger.info("Initialising NewsIngestor …")

        # --- asyncpg ---
        self._DbPool = await asyncpg.create_pool(
            dsn=_DATABASE_URL, min_size=2, max_size=5
        )
        Logger.info("Database pool ready  (%s)", _DATABASE_URL.split("@")[-1])

        # --- Redis ---
        self._Redis = aioredis.from_url(_REDIS_URL, decode_responses=True)
        await self._Redis.ping()
        Logger.info("Redis connected  (%s)", _REDIS_URL)

        # --- aiohttp ---
        self._HttpSession = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        )
        Logger.info("HTTP session created")

    async def Shutdown(self) -> None:
        """Graceful teardown — call on app shutdown."""
        if self._HttpSession and not self._HttpSession.closed:
            await self._HttpSession.close()
        if self._Redis:
            await self._Redis.aclose()
        if self._DbPool:
            await self._DbPool.close()
        Logger.info("NewsIngestor shut down cleanly")

    def IsReady(self) -> bool:
        return all([self._DbPool, self._Redis, self._HttpSession])

    # ── Public API ──────────────────────────────────────────────

    async def IngestForSymbol(self, Symbol: str) -> list[NewsArticle]:
        """
        Fetch the latest news for a single symbol, deduplicate, persist, and
        enqueue each article for sentiment analysis.
        Returns the list of *newly* ingested articles.
        """
        if not self.IsReady():
            raise RuntimeError("NewsIngestor not initialised — call Initialise() first")

        Articles = await self._FetchFromNewsApi(Symbol)
        Logger.info("[%s] Fetched %d articles from NewsAPI", Symbol, len(Articles))

        NewArticles: list[NewsArticle] = []
        for Article in Articles:
            try:
                if await self._IsDuplicate(Article):
                    Logger.debug("[%s] Skipping duplicate: %s", Symbol, Article.SourceUrl)
                    continue

                ScoreId = await self._SaveToDatabase(Article)
                
                from app.NewsSentiment.Tasks import ProcessArticleTask
                article_dict = {
                    "id": ScoreId,
                    "symbol": Article.Symbol,
                    "headline": Article.Headline,
                    "content": Article.Content,
                    "source": Article.SourceUrl
                }
                
                # Enqueue first! If Celery fails, we throw an Exception and NEVER mark as seen,
                # ensuring the article is safely picked up again on the next polling cycle.
                ProcessArticleTask.apply_async(
                    args=[article_dict],
                    queue='nlp'
                )
                
                # Mark seen defensively only after guaranteed dispatch
                await self._MarkSeen(Article)
                
                NewArticles.append(Article)

            except Exception as Exc:
                Logger.error(
                    "[%s] Failed to ingest article '%s': %s",
                    Symbol, Article.Headline[:60], Exc,
                    exc_info=True,
                )

        Logger.info(
            "[%s] Ingested %d new articles (%d duplicates skipped)",
            Symbol, len(NewArticles), len(Articles) - len(NewArticles),
        )
        return NewArticles

    async def IngestAll(self) -> dict[str, int]:
        """Ingest for every symbol in the watchlist. Returns {symbol: count}."""
        Results: dict[str, int] = {}
        for Symbol in _WATCHLIST:
            try:
                New = await self.IngestForSymbol(Symbol)
                Results[Symbol] = len(New)
            except Exception as Exc:
                Logger.error("[%s] Ingestion failed: %s", Symbol, Exc, exc_info=True)
                Results[Symbol] = 0
        return Results

    async def RunForever(self) -> None:
        """
        Blocking poll loop — call from a Celery beat task or as a standalone
        async entry point.
        """
        Logger.info(
            "Starting continuous ingestion  (interval=%ds, symbols=%s)",
            _POLL_INTERVAL, _WATCHLIST,
        )
        while True:
            try:
                await self.IngestAll()
            except Exception as Exc:
                Logger.error("Poll cycle error: %s", Exc, exc_info=True)
            await asyncio.sleep(_POLL_INTERVAL)

    # ── NewsAPI Fetcher ─────────────────────────────────────────

    async def _FetchFromNewsApi(self, Symbol: str) -> list[NewsArticle]:
        """
        Hits NewsAPI /v2/everything for the given stock symbol.
        Returns an empty list (never crashes) if the key is missing or the
        request fails.
        """
        if not _NEWS_API_KEY:
            Logger.warning("NEWS_API_KEY not set — returning empty list for %s", Symbol)
            return []

        Params = {
            "q": f"{Symbol} stock India",
            "apiKey": _NEWS_API_KEY,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 100,
        }

        try:
            async with self._HttpSession.get(_NEWS_API_BASE, params=Params) as Resp:
                if Resp.status != 200:
                    Body = await Resp.text()
                    Logger.error(
                        "[%s] NewsAPI returned %d: %s", Symbol, Resp.status, Body[:200]
                    )
                    return []

                Data = await Resp.json()

        except (aiohttp.ClientError, asyncio.TimeoutError) as Exc:
            Logger.error("[%s] NewsAPI request error: %s", Symbol, Exc)
            return []

        Articles: list[NewsArticle] = []
        for Item in Data.get("articles", []):
            Url = Item.get("url", "")
            if not Url:
                continue
            Articles.append(
                NewsArticle(
                    Symbol=Symbol,
                    Headline=Item.get("title", "") or "",
                    Content=Item.get("description", "") or "",
                    SourceUrl=Url,
                    SourceType="NEWS",
                    PublishedAt=Item.get("publishedAt", datetime.now(timezone.utc).isoformat()),
                )
            )
        return Articles

    # ── Deduplication (Redis) ───────────────────────────────────

    async def _IsDuplicate(self, Article: NewsArticle) -> bool:
        """Check Redis to see if we've already processed this URL."""
        Key = f"news:seen:{Article.UrlHash}"
        return await self._Redis.exists(Key) > 0

    async def _MarkSeen(self, Article: NewsArticle) -> None:
        """Record the URL hash in Redis with a TTL so the set doesn't grow forever."""
        Key = f"news:seen:{Article.UrlHash}"
        await self._Redis.set(Key, "1", ex=_DEDUP_TTL)

    # ── Persistence (asyncpg) ──────────────────────────────────

    async def _SaveToDatabase(self, Article: NewsArticle) -> str:
        """
        Insert into the SentimentScores table with a placeholder sentiment
        (will be overwritten by the NLP worker once scoring completes).
        Matches the schema in scripts/init_schema.sql.
        Returns the generated ScoreId (UUID) as a string.
        """
        Query = """
            INSERT INTO SentimentScores
                (Symbol, SentimentLabel, SentimentScore, Confidence,
                 SourceType, SourceUrl, Headline, ModelVersion, CreatedAt)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING ScoreId
        """
        Record = await self._DbPool.fetchrow(
            Query,
            Article.Symbol,
            "PENDING",              # label placeholder until NLP scores it
            0.0,                    # score placeholder
            0.0,                    # confidence placeholder
            Article.SourceType,
            Article.SourceUrl,
            Article.Headline,
            "pending",              # model version — updated after scoring
            datetime.fromisoformat(Article.PublishedAt),
        )
        Logger.debug("Saved article to DB: %s", Article.Headline[:60])
        return str(Record["scoreid"])

    # ── Sentiment Dispatch ──────────────────────────────────────

    @staticmethod
    def _DispatchSentimentTask(Article: NewsArticle) -> None:
        """
        Enqueue the article for FinBERT scoring via Celery.

        Import is deferred so the module can be loaded even when Celery is not
        fully configured (e.g. during unit tests).
        """
        try:
            from app.NewsSentiment.Tasks import ProcessArticleTask
            ProcessArticleTask.delay(Article.ToDict())
            Logger.debug("Dispatched sentiment task for: %s", Article.Headline[:60])
        except ImportError:
            Logger.warning(
                "SentimentAnalysis.Tasks not available — skipping dispatch for '%s'",
                Article.Headline[:60],
            )
        except Exception as Exc:
            Logger.error("Failed to dispatch sentiment task: %s", Exc, exc_info=True)
