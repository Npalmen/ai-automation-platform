-- Kapitel 2F.1: persistent idempotent external event telemetry

CREATE TABLE IF NOT EXISTS live_eval_external_events (
    event_key             VARCHAR(160) PRIMARY KEY,
    operation_key         VARCHAR(160) NOT NULL,
    tenant_id             VARCHAR(64)  NOT NULL,
    evaluation_run_id     VARCHAR(36)  NOT NULL,
    job_id                VARCHAR(64),
    pipeline_run_id       VARCHAR(36),
    action_operation_id   VARCHAR(36),
    integration_type      VARCHAR(64)  NOT NULL,
    category              VARCHAR(64)  NOT NULL,
    operation             VARCHAR(64)  NOT NULL,
    target                VARCHAR(320),
    outcome               VARCHAR(32)  NOT NULL,
    started_at            TIMESTAMPTZ  NOT NULL,
    completed_at          TIMESTAMPTZ,
    redacted_metadata     JSON         NOT NULL DEFAULT '{}',
    CONSTRAINT fk_live_eval_events_run
        FOREIGN KEY (tenant_id, evaluation_run_id)
        REFERENCES live_eval_runs (tenant_id, evaluation_run_id)
);

CREATE INDEX IF NOT EXISTS ix_live_eval_external_events_run
    ON live_eval_external_events (evaluation_run_id, category);

CREATE INDEX IF NOT EXISTS ix_live_eval_external_events_tenant
    ON live_eval_external_events (tenant_id, category);

CREATE UNIQUE INDEX IF NOT EXISTS uq_live_eval_external_events_operation_succeeded
    ON live_eval_external_events (operation_key)
    WHERE outcome = 'succeeded';
