-- Migration 009: Operator onboarding sessions (Kapitel 9)
-- Idempotent DDL — safe to re-run.

CREATE TABLE IF NOT EXISTS onboarding_sessions (
    id                      VARCHAR(36)  PRIMARY KEY,
    tenant_id               VARCHAR(32)  NOT NULL,
    status                  VARCHAR(32)  NOT NULL,
    current_step            VARCHAR(32)  NOT NULL,
    version                 INTEGER      NOT NULL DEFAULT 1,
    readiness_check_version INTEGER      NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ  NOT NULL,
    updated_at              TIMESTAMPTZ  NOT NULL,
    completed_at            TIMESTAMPTZ,
    activated_at            TIMESTAMPTZ,
    created_by_operator_id  VARCHAR(128) NOT NULL,
    last_updated_by_operator_id VARCHAR(128) NOT NULL,
    cancel_reason           TEXT
);

CREATE INDEX IF NOT EXISTS ix_onboarding_sessions_tenant_id
    ON onboarding_sessions (tenant_id);

CREATE INDEX IF NOT EXISTS ix_onboarding_sessions_status
    ON onboarding_sessions (status);

CREATE UNIQUE INDEX IF NOT EXISTS ux_onboarding_sessions_open_per_tenant
    ON onboarding_sessions (tenant_id)
    WHERE status IN (
        'draft', 'in_progress', 'blocked',
        'ready_for_review', 'ready_for_activation'
    );

CREATE TABLE IF NOT EXISTS onboarding_step_states (
    session_id              VARCHAR(36)  NOT NULL,
    step_key                VARCHAR(32)  NOT NULL,
    step_status             VARCHAR(32)  NOT NULL,
    verification_level      VARCHAR(32)  NOT NULL DEFAULT 'declared',
    blocking_issues         JSON,
    warnings                JSON,
    updated_at              TIMESTAMPTZ  NOT NULL,
    verified_at             TIMESTAMPTZ,
    updated_by_operator_id  VARCHAR(128),
    PRIMARY KEY (session_id, step_key)
);

CREATE INDEX IF NOT EXISTS ix_onboarding_step_states_session_id
    ON onboarding_step_states (session_id);

CREATE TABLE IF NOT EXISTS onboarding_step_drafts (
    session_id              VARCHAR(36)  NOT NULL,
    step_key                VARCHAR(32)  NOT NULL,
    payload                 JSON         NOT NULL,
    updated_at              TIMESTAMPTZ  NOT NULL,
    PRIMARY KEY (session_id, step_key)
);
