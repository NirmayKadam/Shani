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

class OptionsSummaryResponse(BaseModel):
    pcr: float = 0.0
    ce_volume: int = 0
    pe_volume: int = 0
    ce_oi: int = 0
    pe_oi: int = 0
    total_strikes: int = 0
    expiry_dates: list[str] = Field(default_factory=list)
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
