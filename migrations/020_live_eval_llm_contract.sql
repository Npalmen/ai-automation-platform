-- Kapitel 2F.3B.1: fixture_input LLM contract columns and nullable Gmail identity fields

ALTER TABLE live_eval_runs
    ADD COLUMN IF NOT EXISTS llm_provider VARCHAR(64);

ALTER TABLE live_eval_runs
    ADD COLUMN IF NOT EXISTS llm_requested_model VARCHAR(128);

ALTER TABLE live_eval_runs
    ALTER COLUMN expected_sender DROP NOT NULL;

ALTER TABLE live_eval_runs
    ALTER COLUMN expected_recipient DROP NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_live_eval_external_events_operation_in_progress
    ON live_eval_external_events (operation_key)
    WHERE outcome = 'in_progress';
