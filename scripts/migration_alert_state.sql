-- Migration: crossing-based alert state and rule ownership

-- Condition state at the last evaluation; alerts fire on the FALSE/NULL -> TRUE transition.
ALTER TABLE AlertRules ADD COLUMN IF NOT EXISTS last_condition_met BOOLEAN NULL;

-- Owner (Supabase auth user id). NULL for rules created before authentication was enforced.
ALTER TABLE AlertRules ADD COLUMN IF NOT EXISTS user_id UUID NULL;
CREATE INDEX IF NOT EXISTS idx_alert_rules_user ON AlertRules (user_id, is_active);

-- DELTA_BREACH was removed: rules are symbol-level and a symbol has no single delta.
UPDATE AlertRules SET is_active = FALSE WHERE condition_type = 'DELTA_BREACH';
