-- Production pilot P1 ground-truth message reviews (observe-only operational evidence)

CREATE TABLE IF NOT EXISTS production_pilot_message_reviews (
    id                          VARCHAR(36)  PRIMARY KEY,
    tenant_id                   VARCHAR      NOT NULL,
    pilot_phase                 VARCHAR(8)   NOT NULL DEFAULT 'P1',
    provider_message_ref_hash   VARCHAR(64)  NOT NULL,
    intake_event_id             VARCHAR(64),
    job_id                      VARCHAR(64)  NOT NULL,
    reviewed_by                 VARCHAR(128) NOT NULL,
    reviewed_at                 TIMESTAMPTZ  NOT NULL,
    classification_verdict      VARCHAR(16)  NOT NULL,
    extraction_verdict          VARCHAR(16)  NOT NULL,
    routing_verdict             VARCHAR(16)  NOT NULL,
    manual_review_verdict       VARCHAR(16)  NOT NULL,
    shadow_observation_verdict  VARCHAR(16)  NOT NULL,
    match_proposal_verdict      VARCHAR(16)  NOT NULL,
    incident_severity           VARCHAR(16)  NOT NULL DEFAULT 'none',
    error_category              VARCHAR(64),
    business_risk               VARCHAR(16),
    blocks_next_phase           BOOLEAN      NOT NULL DEFAULT FALSE,
    review_version              INTEGER      NOT NULL DEFAULT 1,
    created_at                  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_pilot_message_reviews_tenant_ref_version
    ON production_pilot_message_reviews (tenant_id, provider_message_ref_hash, review_version);

CREATE INDEX IF NOT EXISTS ix_pilot_message_reviews_tenant_job
    ON production_pilot_message_reviews (tenant_id, job_id);

CREATE INDEX IF NOT EXISTS ix_pilot_message_reviews_tenant_reviewed_at
    ON production_pilot_message_reviews (tenant_id, reviewed_at);
