-- Kapitel 2F.1: authoritative live evaluation run registry

CREATE TABLE IF NOT EXISTS live_eval_runs (
    evaluation_run_id     VARCHAR(36)  PRIMARY KEY,
    tenant_id             VARCHAR(64)  NOT NULL,
    scenario_id           VARCHAR(128) NOT NULL,
    attempt_id            INTEGER      NOT NULL,
    transport_mode        VARCHAR(32)  NOT NULL,
    ai_mode               VARCHAR(32)  NOT NULL,
    fixture_bundle_id     VARCHAR(64),
    expected_sender       VARCHAR(320) NOT NULL,
    expected_recipient    VARCHAR(320) NOT NULL,
    status                VARCHAR(32)  NOT NULL DEFAULT 'registered',
    root_gmail_message_id VARCHAR(320),
    root_job_id           VARCHAR(64),
    created_by            VARCHAR(128) NOT NULL,
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    expires_at            TIMESTAMPTZ  NOT NULL,
    config_hash           VARCHAR(64)  NOT NULL,
    CONSTRAINT uq_live_eval_runs_tenant_run UNIQUE (tenant_id, evaluation_run_id)
);

CREATE INDEX IF NOT EXISTS ix_live_eval_runs_tenant_status
    ON live_eval_runs (tenant_id, status);

CREATE INDEX IF NOT EXISTS ix_live_eval_runs_expires_at
    ON live_eval_runs (expires_at);
