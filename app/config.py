# app/config.py — Application configuration
#
# Single source of truth for all environment-driven settings.
# Uses Pydantic v2 Settings with .env file support.

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
    DatabaseUrl: str = Field(
        "postgresql://postgres:postgres@postgres:5432/NexusQuantDB",
        validation_alias="DATABASE_URL"
    )

    # External APIs
    NewsApiKey: str      = Field("", validation_alias="NEWS_API_KEY")

    # NLP Models
    ModelCacheDir: str   = Field("./models", validation_alias="MODEL_CACHE_DIR")
    FinbertModel: str    = Field("ProsusAI/finbert", validation_alias="FINBERT_MODEL")

    # Ingestion
    DefaultSymbols: str       = Field(
        "NIFTY,BANKNIFTY,RELIANCE,INFY,HDFCBANK,TCS,ICICIBANK",
        validation_alias="WATCHLIST_SYMBOLS"
    )
    NewsPollIntervalSeconds: int = Field(120, validation_alias="NEWS_POLL_INTERVAL_SECONDS")
    PricePollIntervalSeconds: int = Field(15, validation_alias="PRICE_POLL_INTERVAL_SECONDS")
    OptionsPollIntervalSeconds: int = Field(30, validation_alias="OPTIONS_POLL_INTERVAL_SECONDS")

    # ── Helpers ────────────────────────────────────────────────

    def GetDefaultSymbolsAsList(self) -> list[str]:
        """Parse DefaultSymbols into a clean list."""
        return [s.strip().upper() for s in self.DefaultSymbols.split(",") if s.strip()]


@lru_cache()
def GetSettings() -> Settings:
    return Settings()
