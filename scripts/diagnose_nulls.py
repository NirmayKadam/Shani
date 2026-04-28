
import asyncio
import json
from shared.infrastructure.redis_client import get_redis_client
from shared.infrastructure.database import GetDatabasePool
from shared.constants import RedisKeys, Timeframe

async def diagnose():
    symbol = "NIFTY"
    print(f"--- Diagnostics for {symbol} ---")
    
    # Check Postgres
    db_pool = await GetDatabasePool()
    async with db_pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM SentimentScores WHERE Symbol = $1", symbol)
        print(f"Postgres: SentimentScores rows for {symbol}: {count}")
        
        recent = await conn.fetch("SELECT CreatedAt, SentimentLabel, sentiment_score FROM SentimentScores WHERE Symbol = $1 ORDER BY CreatedAt DESC LIMIT 5", symbol)
        for r in recent:
            print(f"  - {r['createdat']}: {r['sentimentlabel']} ({r['sentiment_score']})")

    # Check Redis Headlines
    redis = await get_redis_client()
    headlines_count = await redis.zcard(RedisKeys.NEWS_HEADLINES.format(symbol=symbol))
    print(f"Redis: Headlines count for {symbol}: {headlines_count}")

    # Check Redis Aggregates
    for tf in Timeframe:
        key = RedisKeys.SENTIMENT_AGG.format(symbol=symbol, tf=tf.value)
        exists = await redis.exists(key)
        val = await redis.get(key) if exists else None
        print(f"Redis: Aggregate {tf.value} exists: {exists} (Value: {val[:50] if val else 'None'})")

    # Check Redis ML Prediction
    ml_key = RedisKeys.ML_PREDICTION.format(symbol=symbol)
    ml_exists = await redis.exists(ml_key)
    ml_val = await redis.get(ml_key) if ml_exists else None
    print(f"Redis: ML Prediction exists: {ml_exists} (Value: {ml_val[:50] if ml_val else 'None'})")

if __name__ == "__main__":
    asyncio.run(diagnose())
