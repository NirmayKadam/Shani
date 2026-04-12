# app/Config.py
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "populate_by_name": True,
        "extra": "ignore"
    }

    # Application
    AppEnv: str          = Field("development", validation_alias="APP_ENV")
    LogLevel: str        = Field("INFO", validation_alias="LOG_LEVEL")

    # Redis
    RedisUrl: str        = Field("redis://redis:6379/0", validation_alias="REDIS_URL")

    # PostgreSQL
    DatabaseUrl: str = Field("postgresql://postgres:postgres@postgres:5432/postgres", validation_alias="DATABASE_URL")
    
    # External APIs

    # External APIs
    NewsApiKey: str      = Field("", validation_alias="NEWS_API_KEY")
    KiteApiKey: str      = Field("", validation_alias="KITE_API_KEY")
    KiteApiSecret: str   = Field("", validation_alias="KITE_API_SECRET")
    RedditClientId: str  = Field("", validation_alias="REDDIT_CLIENT_ID")
    RedditClientSecret: str = Field("", validation_alias="REDDIT_CLIENT_SECRET")
    RedditUserAgent: str = Field("AlphaStreamsBot/1.0", validation_alias="REDDIT_USER_AGENT")
    TelegramApiId: str   = Field("", validation_alias="TELEGRAM_API_ID")
    TelegramApiHash: str = Field("", validation_alias="TELEGRAM_API_HASH")

    # NLP Models
    ModelCacheDir: str   = Field("./models", validation_alias="MODEL_CACHE_DIR")
    FinbertModel: str    = Field("ProsusAI/finbert", validation_alias="FINBERT_MODEL")
    SummarizerModel: str = Field("sshleifer/distilbart-cnn-12-6", validation_alias="SUMMARIZER_MODEL")

    # Ingestion
    WatchlistSymbols: str       = Field("RELIANCE,INFY,HDFCBANK,TCS", validation_alias="WATCHLIST_SYMBOLS")
    NewsPollIntervalSeconds: int = Field(120, validation_alias="NEWS_POLL_INTERVAL_SECONDS")
    TickPollIntervalSeconds: int = Field(30, validation_alias="TICK_POLL_INTERVAL_SECONDS")

@lru_cache()
def GetSettings() -> Settings:
    return Settings()