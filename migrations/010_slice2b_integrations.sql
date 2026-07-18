-- Migration 010: Slice 2B integrations onboarding (verification, OAuth state, resource bindings)
-- Idempotent DDL — safe to re-run.

ALTER TABLE onboarding_sessions
    ADD COLUMN IF NOT EXISTS integration_state_revision INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS onboarding_oauth_states (
    state_id                VARCHAR(64)  PRIMARY KEY,
    state_hash              TEXT         NOT NULL,
    session_id              VARCHAR(36)  NOT NULL,
    tenant_id               VARCHAR(32)  NOT NULL,
    operator_id             VARCHAR(128) NOT NULL,
    provider                VARCHAR(32)  NOT NULL,
    redirect_target         TEXT         NOT NULL,
    expires_at              TIMESTAMPTZ  NOT NULL,
    consumed_at             TIMESTAMPTZ,
    created_at              TIMESTAMPTZ  NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_onboarding_oauth_states_session
    ON onboarding_oauth_states (session_id, provider);

CREATE INDEX IF NOT EXISTS ix_onboarding_oauth_states_expires
    ON onboarding_oauth_states (expires_at);

CREATE TABLE IF NOT EXISTS onboarding_integration_verifications (
    session_id                      VARCHAR(36)  NOT NULL,
    integration_key                 VARCHAR(32)  NOT NULL,
    verification_status             VARCHAR(32)  NOT NULL,
    source_class                    VARCHAR(32)  NOT NULL,
    verified_at                     TIMESTAMPTZ,
    verified_by_operator_id         VARCHAR(128),
    config_fingerprint              VARCHAR(64),
    integration_state_revision_at_verify INTEGER,
    error_code                      VARCHAR(64),
    environment_safe_metadata         JSON,
    updated_at                      TIMESTAMPTZ  NOT NULL,
    PRIMARY KEY (session_id, integration_key)
);

CREATE INDEX IF NOT EXISTS ix_onboarding_integration_verifications_session
    ON onboarding_integration_verifications (session_id);

CREATE TABLE IF NOT EXISTS tenant_resource_bindings (
    id                      VARCHAR(36)  PRIMARY KEY,
    resource_type           VARCHAR(64)  NOT NULL,
    resource_id             VARCHAR(256) NOT NULL,
    tenant_id               VARCHAR(32)  NOT NULL,
    session_id              VARCHAR(36)  NOT NULL,
    status                  VARCHAR(16)  NOT NULL,
    bound_at                TIMESTAMPTZ  NOT NULL,
    bound_by_operator_id    VARCHAR(128) NOT NULL,
    released_at             TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_tenant_resource_bindings_active
    ON tenant_resource_bindings (resource_type, resource_id)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS ix_tenant_resource_bindings_tenant
    ON tenant_resource_bindings (tenant_id, status);
