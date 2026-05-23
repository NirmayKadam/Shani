"""
File Overview: Pydantic response models and schemas for the analytics API.

All Functions/Classes:
- ResponseMetadata: Base schema for all API responses. Take status/source and send to validated JSON response.
- MarketDataResponse: Stores price and volume metrics. Take raw data and send to validated object.
- HeadlineItem: Stores single news items with sentiment scoring. Take raw headline data and send to validated object.
- SentimentTimeframeData: Stores aggregated sentiment metrics for a specific timeframe. Take aggregation data and send to validated object.
- SentimentResponse: Compiles multi-timeframe sentiment data. Take intraday/daily/weekly/monthly payloads and send to validated object.
- OptionsSummaryResponse: Stores PCR and option volume/OI stats. Take calculation results and send to validated object.
- TechnicalForecastResponse: Stores ML inference results. Take prediction metrics and send to validated object.
- AnalysisResponse: Final unified response schema. Take all analytical components and send to client.
- SymbolsResponse: Returns recommended symbols. Take list from settings and send to client.
- ErrorEnvelope: Standardized error response. Take error details and send to validated error object.

Endpoints/APIs:
- Definition layer for all /v1/ analytics endpoints.

Database Tables:
- None.
"""
from typing import Optional


from pydantic import BaseModel, Field


class ResponseMetadata(BaseModel):
    generated_at: str = ""
    source: str = ""
    stale: bool = True
    partial: bool = True
    status: str = "COMPLETED"  # COMPLETED, CALCULATING, FAILED


# ── Market Data ─────────────────────────────────────────────────

class MarketDataResponse(BaseModel):
    last_price: float
    open: float
    high: float
    low: float
    volume: int
    previous_close: float
    change_percent: float
    currency: str = "INR"
    market_status: str
    last_updated: str


# ── Headlines ──────────────────────────────────────────────────

class HeadlineItem(BaseModel):
    headline: str
    source_name: str
    published_at: str
    sentiment_label: str
    sentiment_score: float
    confidence: float


# ── Sentiment Aggregation ──────────────────────────────────────

class SentimentTimeframeData(BaseModel):
    label: str
    avg_score: float
    bullish_pct: float
    bearish_pct: float
    neutral_pct: float
    count: int
    trend: str = "STABLE"


class SentimentResponse(BaseModel):
    intraday: SentimentTimeframeData
    daily: SentimentTimeframeData
    weekly: SentimentTimeframeData
    monthly: SentimentTimeframeData


# ── Options Summary ────────────────────────────────────────────

class OptionTick(BaseModel):
    strike: float
    type: str  # CE/PE
    last_price: float
    iv: float
    oi: int
    volume: int
    expiry: str

class OptionsSummaryResponse(BaseModel):
    pcr: float = 0.0
    ce_volume: int = 0
    pe_volume: int = 0
    ce_oi: int = 0
    pe_oi: int = 0
    total_strikes: int = 0
    expiry_dates: list[str] = Field(default_factory=list)
    chain: list[OptionTick] = Field(default_factory=list)
    available: bool = False
    last_updated: str = ""


# ── Technical Forecast ──────────────────────────────────────────

class TechnicalForecastResponse(BaseModel):
    strategy: str
    prediction: str
    confidence: float
    confluence_status: str


# ── Full Analysis Response ─────────────────────────────────────

class FreshnessMetadata(ResponseMetadata):
    pass


class AnalysisResponse(ResponseMetadata):
    symbol: str
    market_data: Optional[MarketDataResponse] = None
    headlines: list[HeadlineItem] = Field(default_factory=list)
    sentiment: Optional[SentimentResponse] = None
    options_summary: Optional[OptionsSummaryResponse] = None
    technical_forecast: Optional[TechnicalForecastResponse] = None


# ── Symbols Response ───────────────────────────────────────────

class SymbolsResponse(ResponseMetadata):
    symbols: list[str] = Field(default_factory=list)
    count: int


# ── Error Envelope ──────────────────────────────────────────────

class ErrorEnvelope(ResponseMetadata):
    error: str
    code: str
    details: dict | list[dict] | None = None
