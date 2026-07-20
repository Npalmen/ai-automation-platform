-- Onboarding 2.0: customer integration invitations
CREATE TABLE IF NOT EXISTS integration_invitations (
    id                          VARCHAR(36)  PRIMARY KEY,
    tenant_id                   VARCHAR(32)  NOT NULL,
    integration_key             VARCHAR(32)  NOT NULL,
    contact_name                VARCHAR(256),
    contact_email               VARCHAR(256) NOT NULL,
    token_hash                  TEXT         NOT NULL,
    status                      VARCHAR(32)  NOT NULL DEFAULT 'pending',
    expires_at                  TIMESTAMPTZ  NOT NULL,
    revoked_at                  TIMESTAMPTZ,
    consumed_at                 TIMESTAMPTZ,
    connected_account_email     VARCHAR(256),
    created_by_operator_id      VARCHAR(128) NOT NULL,
    created_at                  TIMESTAMPTZ  NOT NULL,
    message_optional            TEXT
);
CREATE INDEX IF NOT EXISTS ix_integration_invitations_tenant ON integration_invitations (tenant_id, integration_key);
CREATE INDEX IF NOT EXISTS ix_integration_invitations_status ON integration_invitations (status, expires_at);
CREATE UNIQUE INDEX IF NOT EXISTS ux_integration_invitations_token_hash ON integration_invitations (token_hash);
