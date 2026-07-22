-- Kapitel 2F.1: record when a live-eval run was atomically claimed

ALTER TABLE live_eval_runs
    ADD COLUMN IF NOT EXISTS activated_at TIMESTAMPTZ;
