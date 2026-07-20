-- Slice B: integration selection structure (no tenant data backfill in SQL).
-- Application service classifies tenants and writes settings.integrations.selections.

CREATE TABLE IF NOT EXISTS integration_selection_backfill_runs (
    id              VARCHAR(36)  PRIMARY KEY,
    started_at      TIMESTAMPTZ  NOT NULL,
    completed_at    TIMESTAMPTZ,
    dry_run         BOOLEAN      NOT NULL DEFAULT FALSE,
    status          VARCHAR(32)  NOT NULL,
    tenants_seen    INTEGER      NOT NULL DEFAULT 0,
    tenants_updated INTEGER      NOT NULL DEFAULT 0,
    tenants_skipped INTEGER      NOT NULL DEFAULT 0,
    report_json     JSON         NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS ix_integration_selection_backfill_runs_started
    ON integration_selection_backfill_runs (started_at DESC);
