-- Migration 011: Operator alerts (Kapitel 10)
-- Idempotent DDL — safe to re-run.

CREATE TABLE IF NOT EXISTS operator_alerts (
    id                          VARCHAR(36)  PRIMARY KEY,
    alert_type                  VARCHAR(64)  NOT NULL,
    deduplication_key           VARCHAR(256) NOT NULL,
    scope_type                  VARCHAR(32)  NOT NULL,
    tenant_id                   VARCHAR(32),
    related_job_id              VARCHAR(64),
    integration_key             VARCHAR(32),
    severity                    VARCHAR(16)  NOT NULL,
    status                      VARCHAR(16)  NOT NULL,
    title                       VARCHAR(256) NOT NULL,
    summary                     TEXT         NOT NULL,
    safe_details                JSON         NOT NULL DEFAULT '{}',
    source                      VARCHAR(64)  NOT NULL DEFAULT 'evaluation_engine',
    source_class                VARCHAR(32)  NOT NULL DEFAULT 'intern_db_detected',
    source_version              VARCHAR(32)  NOT NULL DEFAULT '1',
    first_detected_at           TIMESTAMPTZ  NOT NULL,
    last_detected_at            TIMESTAMPTZ  NOT NULL,
    occurrence_count            INTEGER      NOT NULL DEFAULT 1,
    last_evaluated_at           TIMESTAMPTZ  NOT NULL,
    acknowledged_at             TIMESTAMPTZ,
    acknowledged_by             VARCHAR(128),
    snoozed_until               TIMESTAMPTZ,
    resolved_at                 TIMESTAMPTZ,
    resolution_reason           TEXT,
    current_fingerprint         VARCHAR(128) NOT NULL,
    created_at                  TIMESTAMPTZ  NOT NULL,
    updated_at                  TIMESTAMPTZ  NOT NULL,
    version                     INTEGER      NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS ix_operator_alerts_status_severity
    ON operator_alerts (status, severity, last_detected_at DESC);

CREATE INDEX IF NOT EXISTS ix_operator_alerts_tenant_status
    ON operator_alerts (tenant_id, status);

CREATE INDEX IF NOT EXISTS ix_operator_alerts_alert_type
    ON operator_alerts (alert_type);

CREATE UNIQUE INDEX IF NOT EXISTS ux_operator_alerts_active_dedup_key
    ON operator_alerts (deduplication_key)
    WHERE status IN ('open', 'acknowledged', 'snoozed', 'suppressed');

CREATE TABLE IF NOT EXISTS alert_evaluation_runs (
    run_id                      VARCHAR(36)  PRIMARY KEY,
    started_at                  TIMESTAMPTZ  NOT NULL,
    completed_at                TIMESTAMPTZ,
    status                      VARCHAR(32)  NOT NULL,
    scope                       VARCHAR(32)  NOT NULL DEFAULT 'platform',
    dry_run                     BOOLEAN      NOT NULL DEFAULT FALSE,
    evaluator_version           VARCHAR(32)  NOT NULL DEFAULT '1',
    created_count               INTEGER      NOT NULL DEFAULT 0,
    updated_count               INTEGER      NOT NULL DEFAULT 0,
    resolved_count              INTEGER      NOT NULL DEFAULT 0,
    error_count                 INTEGER      NOT NULL DEFAULT 0,
    evaluator_results_json      JSON         NOT NULL DEFAULT '[]',
    safe_error_summary          TEXT,
    triggered_by_operator_id    VARCHAR(128)
);

CREATE INDEX IF NOT EXISTS ix_alert_evaluation_runs_started_at
    ON alert_evaluation_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS operator_digests (
    id                          VARCHAR(36)  PRIMARY KEY,
    digest_date                 DATE         NOT NULL,
    timezone                    VARCHAR(64)  NOT NULL DEFAULT 'Europe/Stockholm',
    generated_at                TIMESTAMPTZ  NOT NULL,
    period_start                TIMESTAMPTZ  NOT NULL,
    period_end                  TIMESTAMPTZ  NOT NULL,
    content_json                JSON         NOT NULL DEFAULT '{}',
    delivery_status             VARCHAR(32)  NOT NULL DEFAULT 'pending',
    created_at                  TIMESTAMPTZ  NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_operator_digests_digest_date
    ON operator_digests (digest_date DESC);

CREATE TABLE IF NOT EXISTS notification_deliveries (
    id                          VARCHAR(36)  PRIMARY KEY,
    alert_id                    VARCHAR(36),
    digest_id                   VARCHAR(36),
    channel                     VARCHAR(32)  NOT NULL,
    recipient_ref               VARCHAR(256) NOT NULL,
    status                      VARCHAR(32)  NOT NULL DEFAULT 'pending',
    attempt_count               INTEGER      NOT NULL DEFAULT 0,
    next_attempt_at             TIMESTAMPTZ,
    sent_at                     TIMESTAMPTZ,
    idempotency_key             VARCHAR(256) NOT NULL,
    safe_error_code             VARCHAR(64),
    created_at                  TIMESTAMPTZ  NOT NULL,
    updated_at                  TIMESTAMPTZ  NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_notification_deliveries_idempotency
    ON notification_deliveries (idempotency_key);

CREATE INDEX IF NOT EXISTS ix_notification_deliveries_status
    ON notification_deliveries (status, next_attempt_at);
