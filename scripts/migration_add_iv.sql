-- Migration: Add IV and Underlying Price to TickData
ALTER TABLE TickData ADD COLUMN IF NOT EXISTS ImpliedVolatility DECIMAL(10,4);
ALTER TABLE TickData ADD COLUMN IF NOT EXISTS UnderlyingPrice DECIMAL(12,2);

-- Retention for tickdata is 90 days, set in init_schema.sql and migration_add_indexes.sql.
SELECT add_retention_policy('tickdata', INTERVAL '90 days', if_not_exists => true);
