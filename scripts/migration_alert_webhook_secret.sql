-- Migration: per-rule webhook signing secret
-- Webhook payloads are signed with HMAC-SHA256 using this secret (shown to the owner once, at
-- creation). Previously the rule id was the key, and the rule id is returned by the API.
ALTER TABLE AlertRules ADD COLUMN IF NOT EXISTS webhook_secret TEXT NULL;
