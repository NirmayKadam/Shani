-- TimescaleDB hypertable for tick data
CREATE TABLE IF NOT EXISTS TickData (
    Timestamp       TIMESTAMPTZ     NOT NULL,
    Symbol          VARCHAR(20)     NOT NULL,
    Exchange        VARCHAR(5)      NOT NULL,
    InstrumentType  VARCHAR(5)      NOT NULL,  -- EQ | FUT | CE | PE
    LastPrice       DECIMAL(12,2),
    OpenInterest    BIGINT          DEFAULT 0,
    Volume          BIGINT,
    ExpiryDate      DATE,
    StrikePrice     DECIMAL(10,2)
);

-- Idempotent hypertable creation
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM timescaledb_information.hypertables WHERE hypertable_name = 'tickdata') THEN
        PERFORM create_hypertable('tickdata', 'timestamp');
    END IF;
END $$;

-- Processed sentiment scores
CREATE TABLE IF NOT EXISTS SentimentScores (
    ScoreId         UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    Symbol          VARCHAR(20)     NOT NULL,
    SentimentLabel  VARCHAR(10)     NOT NULL,  -- BULLISH | BEARISH | NEUTRAL
    SentimentScore  DECIMAL(5,4)    NOT NULL,
    Confidence      DECIMAL(5,4)    NOT NULL,
    SourceType      VARCHAR(10)     NOT NULL,  -- NEWS | REDDIT | TELEGRAM
    SourceUrl       TEXT,
    Headline        TEXT,
    ModelVersion    VARCHAR(50),
    CreatedAt       TIMESTAMPTZ     DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sentiment_symbol_time ON SentimentScores (Symbol, CreatedAt DESC);

-- Detected events
CREATE TABLE IF NOT EXISTS DetectedEvents (
    EventId         UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    Symbol          VARCHAR(20)     NOT NULL,
    EventType       VARCHAR(30)     NOT NULL,
    Headline        TEXT,
    EventDate       DATE,
    SourceType      VARCHAR(10),
    Confidence      DECIMAL(5,4)    DEFAULT 1.0,
    DetectedAt      TIMESTAMPTZ     DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_events_symbol_time ON DetectedEvents (Symbol, DetectedAt DESC);

-- Alert rules (user-defined)
CREATE TABLE IF NOT EXISTS AlertRules (
    RuleId          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    Symbol          VARCHAR(20)     NOT NULL,
    ConditionField  VARCHAR(30)     NOT NULL,
    ConditionOp     VARCHAR(10)     NOT NULL,
    ConditionValue  TEXT            NOT NULL,
    WebhookUrl      TEXT,
    CooldownSecs    INT             DEFAULT 300,
    IsActive        BOOLEAN         DEFAULT TRUE,
    CreatedAt       TIMESTAMPTZ     DEFAULT NOW()
);
