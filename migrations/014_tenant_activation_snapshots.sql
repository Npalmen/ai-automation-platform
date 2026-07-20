-- Onboarding 2.0: immutable activation snapshots (append-only)
CREATE TABLE IF NOT EXISTS tenant_activation_snapshots (
    id                          VARCHAR(36)  PRIMARY KEY,
    tenant_id                   VARCHAR(32)  NOT NULL,
    config_version              INTEGER      NOT NULL,
    plan_hash                   VARCHAR(64)  NOT NULL,
    readiness_check_version     INTEGER      NOT NULL,
    snapshot_json               JSON         NOT NULL,
    activated_by_operator_id    VARCHAR(128) NOT NULL,
    activated_at                TIMESTAMPTZ  NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_tenant_activation_snapshots_tenant ON tenant_activation_snapshots (tenant_id, activated_at DESC);
