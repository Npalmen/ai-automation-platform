-- R4 reviewed-live registration: persist authoritative campaign/execution/manifest + context

ALTER TABLE live_eval_runs
    ADD COLUMN IF NOT EXISTS campaign_type VARCHAR(128),
    ADD COLUMN IF NOT EXISTS execution_mode VARCHAR(64),
    ADD COLUMN IF NOT EXISTS manifest_hash VARCHAR(64),
    ADD COLUMN IF NOT EXISTS registration_context JSONB;

CREATE INDEX IF NOT EXISTS ix_live_eval_runs_campaign_type
    ON live_eval_runs (campaign_type)
    WHERE campaign_type IS NOT NULL;
