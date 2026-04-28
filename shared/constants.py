"""
File Overview: Shared enums, channel names, and configuration constants for Redis Pub/Sub and Market Data.

All Functions/Classes:
- Channels (class): Redis Pub/Sub channel templates.
- Streams (class): Redis Stream names for durable events.
- StreamGroups (class): Consumer-group names for stream processing.
- SentimentLabel, MarketStatus, Timeframe, PriceTriggerType, OptionType (Enums): Domain status and category codes.
- RedisKeys (class): Redis key templates for cached data.
- TTL (class): Expiration times for cached items.

Endpoints/APIs:
- None.

Database Tables:
- None.
"""


from enum import Enum


# ── Redis Pub/Sub Channel Names ────────────────────────────────

class Channels:
    """Redis Pub/Sub channel name templates. Use .format(symbol=...) to build."""

    # Ingestion domain publishes:
    HEADLINE_FETCHED      = "headlines.fetched.{symbol}"
    PRICE_UPDATED         = "market.price_updated.{symbol}"
    OPTIONS_UPDATED       = "market.options_updated.{symbol}"
    PRICE_TRIGGER         = "market.price_trigger.{symbol}"

    # Sentiment domain publishes:
    SENTIMENT_SCORED      = "sentiment.scored.{symbol}"
    AGGREGATE_UPDATED     = "sentiment.aggregate_updated.{symbol}"


# ── Redis Streams (Durable Topics) ────────────────────────────

class Streams:
    """Redis Stream names for durable/replayable cross-domain events."""

    # Ingestion -> NLP (critical)
    HEADLINE_FETCHED      = "stream:headlines.fetched"
    PRICE_TRIGGER         = "stream:market.price_trigger"

    # NLP -> API/read model consumers (critical)
    SENTIMENT_SCORED      = "stream:sentiment.scored"
    AGGREGATE_UPDATED     = "stream:sentiment.aggregate_updated"
    ANALYSIS_REFRESH_REQUESTED = "stream:analysis.refresh_requested"

    # Dead-letter topics
    INGESTION_TO_NLP_DLQ  = "stream:dlq:ingestion_to_nlp"
    NLP_TO_API_DLQ        = "stream:dlq:nlp_to_api"


class StreamGroups:
    """Consumer-group names for durable stream processing."""

    INGESTION_TO_NLP = "cg:ingestion_to_nlp"
    NLP_TO_API = "cg:nlp_to_api"


# ── Enums ──────────────────────────────────────────────────────

class SentimentLabel(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class MarketStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PRE_MARKET = "PRE_MARKET"
    POST_MARKET = "POST_MARKET"


class Timeframe(str, Enum):
    INTRADAY = "intraday"   # Last 6 hours
    DAILY    = "daily"      # Last 24 hours
    WEEKLY   = "weekly"     # Last 7 days
    MONTHLY  = "monthly"    # Last 30 days


class PriceTriggerType(str, Enum):
    FLASH_DROP      = "FLASH_DROP"
    SPIKE_UP        = "SPIKE_UP"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    VOLUME_ANOMALY  = "VOLUME_ANOMALY"


class OptionType(str, Enum):
    CE = "CE"
    PE = "PE"


# ── Redis Key Prefixes ────────────────────────────────────────

class RedisKeys:
    """Redis key templates for cached data. Use .format() to build."""

    # Ingestion domain owns:
    MARKET_PRICE       = "market:price:{symbol}"            # Today's OHLCV snapshot
    MARKET_OPTIONS     = "market:options:{symbol}"           # Latest option chain
    NEWS_HEADLINES     = "headlines:scored:{symbol}"          # Sorted set of scored headlines
    NEWS_DEDUP         = "news:seen:{url_hash}"              # Deduplication key

    # Sentiment domain owns:
    SENTIMENT_LATEST   = "sentiment:latest:{symbol}"         # Latest individual score
    SENTIMENT_EMA      = "sentiment:ema:{symbol}"            # EMA value
    SENTIMENT_AGG      = "sentiment:aggregate:{symbol}:{tf}" # Aggregate per timeframe

    # ML domain owns:
    ML_PREDICTION      = "ml:prediction:{symbol}"            # CNN forecast


# ── TTLs (seconds) ────────────────────────────────────────────

class TTL:
    MARKET_PRICE     = 86400    # 24h — refreshed every poll cycle
    MARKET_OPTIONS   = 600      # 10 min during market hours
    HEADLINES        = 86400    # 24h — sorted set trimmed by count
    SENTIMENT_LATEST = 300      # 5 min
    SENTIMENT_EMA    = 86400    # 24h
    SENTIMENT_AGG    = 300      # 5 min — recomputed frequently
    NEWS_DEDUP       = 86400    # 24h
    ML_PREDICTION    = 86400    # 24h


# ── Index Symbols (use option-chain-indices endpoint) ─────────

INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY"}
