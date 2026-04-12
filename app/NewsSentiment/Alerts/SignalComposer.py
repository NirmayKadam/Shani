# app/MarketSignals/SignalComposer.py
import logging
from typing import Optional
from app.Infrastructure.DatabaseClient import GetDatabasePool
from app.Infrastructure.RedisClient import GetRedisClient
import json

Logger = logging.getLogger(__name__)

# Thresholds for generating an explicit trading signal event
STRONG_BULLISH_THRESHOLD = 0.7
STRONG_BEARISH_THRESHOLD = -0.7

class SignalComposer:
    def __init__(self):
        self.WindowSize = 20

    async def ProcessNewSentiment(self, payload: dict) -> Optional[dict]:
        """
        Triggered when a new sentiment score is finalised.
        Calculates the moving average and returns a Signal Event dict if a
        threshold is crossed, otherwise returns None.
        """
        symbol = payload.get("symbol")
        if not symbol:
            return None

        # 1. Fetch last N scores
        Pool = await GetDatabasePool()
        Query = """
            SELECT SentimentScore 
            FROM SentimentScores 
            WHERE Symbol = $1 AND SentimentLabel != 'PENDING'
            ORDER BY CreatedAt DESC 
            LIMIT $2
        """
        Records = await Pool.fetch(Query, symbol, self.WindowSize)
        if not Records:
            return None

        # Grab the previous EMA from Redis
        Redis = await GetRedisClient()
        CacheKey = f"signals:ema:{symbol}"
        PreviousEmaStr = await Redis.get(CacheKey)

        # Calculate Exponential Moving Average of sentiment
        latest_score = float(Records[0]['sentimentscore'])

        if PreviousEmaStr is None:
            # Seed the initial EMA using an SMA of available records
            scores = [float(r['sentimentscore']) for r in Records]
            ema = sum(scores) / len(scores)
            PreviousEma = None
        else:
            PreviousEma = float(PreviousEmaStr)
            multiplier = 2.0 / (self.WindowSize + 1)
            ema = (latest_score - PreviousEma) * multiplier + PreviousEma

        # Update Redis with new EMA
        await Redis.set(CacheKey, str(ema), ex=3600*24) # 24h TTL

        if PreviousEma is None:
            Logger.debug(f"[{symbol}] Initial EMA cache seeded: {ema:.3f}. Skipping crossover alerts.")
            return None
            
        Logger.debug(f"[{symbol}] EMA updated: {ema:.3f} (Prev: {PreviousEma:.3f}).")

        # 2. Check for Signal Crossovers
        SignalEvent = None
        Headline = ""

        if ema >= STRONG_BULLISH_THRESHOLD and PreviousEma < STRONG_BULLISH_THRESHOLD:
            SignalEvent = "STRONG_BULLISH_CROSSOVER"
            Headline = f"{symbol} sentiment exponential moving average crossed into Strong Bullish territory ({ema:.2f})"
        
        elif ema <= STRONG_BEARISH_THRESHOLD and PreviousEma > STRONG_BEARISH_THRESHOLD:
            SignalEvent = "STRONG_BEARISH_CROSSOVER"
            Headline = f"{symbol} sentiment exponential moving average crossed into Strong Bearish territory ({ema:.2f})"

        # 3. Save Event to Postgres if generated
        if SignalEvent:
            EventQuery = """
                INSERT INTO DetectedEvents 
                    (Symbol, EventType, Headline, SourceType, Confidence)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING EventId
            """
            EventId = await Pool.fetchval(
                EventQuery, 
                symbol, 
                SignalEvent, 
                Headline, 
                "SYSTEM", 
                1.0
            )
            Logger.info(f"🚀 SIGNAL GENERATED: {Headline}")
            
            return {
                "event_id": str(EventId),
                "symbol": symbol,
                "event_type": SignalEvent,
                "headline": Headline,
                "ema_value": ema
            }
            
        return None
