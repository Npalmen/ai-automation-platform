-- Kapitel 2C: append-only decision trace (DEC-034)
-- tenant_id/job_id types align with jobs + approval_requests (unbounded VARCHAR).

CREATE TABLE IF NOT EXISTS decision_records (
    decision_id              VARCHAR(36)  PRIMARY KEY,
    tenant_id                VARCHAR      NOT NULL,
    job_id                   VARCHAR      NOT NULL,

    event_sequence           BIGINT       GENERATED ALWAYS AS IDENTITY,
    pipeline_run_id          VARCHAR(36)  NOT NULL,
    parent_pipeline_run_id   VARCHAR(36),
    stage_sequence           SMALLINT     NOT NULL,

    record_type              VARCHAR(48)  NOT NULL,
    source                   VARCHAR(32)  NOT NULL,

    processor_name           VARCHAR(64),
    recommendation           VARCHAR(32),
    policy_authorization     VARCHAR(32),
    policy_decision          VARCHAR(32),
    action_type              VARCHAR(64),
    action_operation_id      VARCHAR(36),
    action_fingerprint       VARCHAR(128),
    fingerprint_key_version  SMALLINT,
    action_authorization     VARCHAR(32),
    execution_phase          VARCHAR(16),
    execution_status         VARCHAR(32),

    confidence               DOUBLE PRECISION,
    reason_codes             JSON         NOT NULL DEFAULT '[]',

    tenant_config_version    INTEGER,
    code_version             VARCHAR(64)  NOT NULL,
    service_profile_type     VARCHAR(64),
    prompt_name              VARCHAR(64),
    prompt_version           VARCHAR(32),
    prompt_hash              VARCHAR(64),
    model_provider           VARCHAR(32),
    model_name               VARCHAR(64),

    idempotency_key          VARCHAR(160) NOT NULL,
    supersedes_decision_id   VARCHAR(36),

    job_status_at_record     VARCHAR(32)  NOT NULL,
    metadata                 JSON         NOT NULL DEFAULT '{}',
    created_at               TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_decision_records_idempotency
    ON decision_records (tenant_id, idempotency_key);

CREATE INDEX IF NOT EXISTS ix_decision_records_tenant_job_event
    ON decision_records (tenant_id, job_id, event_sequence);

CREATE INDEX IF NOT EXISTS ix_decision_records_pipeline_run
    ON decision_records (tenant_id, pipeline_run_id, stage_sequence);

CREATE INDEX IF NOT EXISTS ix_decision_records_action_operation
    ON decision_records (tenant_id, action_operation_id)
    WHERE action_operation_id IS NOT NULL;
