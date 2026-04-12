# app/SentimentAnalysis/Tasks.py
import asyncio
import json
import logging
from app.CeleryApp import CeleryApp

Logger = logging.getLogger(__name__)

@CeleryApp.task(name='sentiment.process_article', queue='nlp', bind=True)
def ProcessArticleTask(self, article_dict: dict):
    try:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        loop.run_until_complete(_ProcessArticleAsync(article_dict))
    except Exception as exc:
        Logger.error(f"Task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60, max_retries=3)

async def _ProcessArticleAsync(article_dict: dict):
    from app.NewsSentiment.AI_Engine.FinBertClient import FinBertClient
    from app.Infrastructure.RedisClient import GetRedisClient
    from app.Infrastructure.DatabaseClient import GetDatabasePool

    ArticleId = article_dict.get('id')
    Symbol    = article_dict.get('symbol')
    Headline  = article_dict.get('headline', '')
    Content   = article_dict.get('content', '')
    Source    = article_dict.get('source', '')

    if not Symbol or not ArticleId:
        Logger.warning("Invalid payload, skipping.")
        return

    Text = f"{Headline} {Content}"[:512]

    # 1. Run FinBERT inference
    Client  = FinBertClient.GetInstance()
    Results = await Client.ScoreBatch([Text])
    if not Results:
        return

    Label = Results[0]['Label']
    RawScore = Results[0]['Score']

    # Convert confidence probability to polarity (-1.0 to 1.0)
    LabelUpper = Label.upper()
    if LabelUpper in ["NEGATIVE", "BEARISH"]:
        Score = -RawScore
    elif LabelUpper in ["NEUTRAL", "NONE"]:
        Score = 0.0
    else:
        Score = RawScore

    # 2. Write to Redis hot path
    Redis    = await GetRedisClient()
    CacheKey = f"sentiment:{Symbol.upper()}:latest"
    Payload  = {
        "Symbol":    Symbol.upper(),
        "Label":     Label,
        "Score":     Score,
        "Headline":  Headline,
        "Source":    Source,
        "Timestamp": article_dict.get('timestamp', '')
    }
    await Redis.set(CacheKey, json.dumps(Payload), ex=300)

    # 3. Update PostgreSQL row
    Pool = await GetDatabasePool()
    await Pool.execute(
        "UPDATE SentimentScores SET SentimentLabel=$1, SentimentScore=$2 WHERE ScoreId=$3::uuid",
        Label, Score, ArticleId
    )

    Logger.info(f"Scored {Symbol}: {Label} ({Score:.3f})")

    # 4. Emit Event to Market Signals Engine (Event-Driven)
    try:
        from app.NewsSentiment.Tasks import ComposeSignalTask
        payload = {
            "symbol": Symbol.upper(),
            "latest_score": Score,
            "latest_label": Label,
            "article_id": ArticleId
        }
        ComposeSignalTask.apply_async(
            args=[payload],
            queue='signals'
        )
        Logger.debug(f"Emitted ComposeSignalTask for {Symbol}")
    except ImportError:
        Logger.warning("MarketSignals.Tasks not found - skipping signal composition.")
    except Exception as e:
        Logger.error(f"Failed to emit signal task: {e}")