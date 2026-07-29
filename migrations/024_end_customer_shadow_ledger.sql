-- Shadow observation ledger for Testbot F2 (isolated from verified customer domain).

CREATE TABLE IF NOT EXISTS end_customer_shadow_observations (
    observation_id           VARCHAR(36)  PRIMARY KEY,
    tenant_id                VARCHAR(64)  NOT NULL,
    campaign_run_id          VARCHAR(64),
    scenario_execution_id    VARCHAR(128),
    source_provider          VARCHAR(64)  NOT NULL,
    source_message_id        VARCHAR(320) NOT NULL,
    source_thread_id         VARCHAR(320),
    source_event_id          VARCHAR(128),
    extraction_version       VARCHAR(32)  NOT NULL DEFAULT 'v1',
    observation_type         VARCHAR(64)  NOT NULL DEFAULT 'intake_message',
    state                    VARCHAR(32)  NOT NULL,
    raw_payload_hash         VARCHAR(64)  NOT NULL,
    normalized_payload_hash  VARCHAR(64)  NOT NULL,
    confidence               DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    model_name               VARCHAR(128),
    model_prompt_version     VARCHAR(64),
    cleanup_eligible         BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at               TIMESTAMPTZ  NOT NULL,
    updated_at               TIMESTAMPTZ  NOT NULL,
    rejected_at              TIMESTAMPTZ,
    rejected_by              VARCHAR(128),
    CONSTRAINT uq_shadow_observation_idempotency
        UNIQUE (tenant_id, source_provider, source_message_id, extraction_version, observation_type)
);

CREATE INDEX IF NOT EXISTS ix_shadow_observations_tenant_state
    ON end_customer_shadow_observations (tenant_id, state);
CREATE INDEX IF NOT EXISTS ix_shadow_observations_campaign
    ON end_customer_shadow_observations (tenant_id, campaign_run_id);

CREATE TABLE IF NOT EXISTS end_customer_shadow_identity_signals (
    signal_id                VARCHAR(36)  PRIMARY KEY,
    tenant_id                VARCHAR(64)  NOT NULL,
    observation_id           VARCHAR(36)  NOT NULL REFERENCES end_customer_shadow_observations(observation_id) ON DELETE CASCADE,
    signal_type              VARCHAR(64)  NOT NULL,
    raw_value_redacted       VARCHAR(512) NOT NULL,
    normalized_value         VARCHAR(512),
    confidence               DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    source_path              VARCHAR(256),
    trust_level              VARCHAR(32)  NOT NULL DEFAULT 'proposed',
    created_at               TIMESTAMPTZ  NOT NULL,
    CONSTRAINT uq_shadow_signal_idempotency
        UNIQUE (tenant_id, observation_id, signal_type, normalized_value)
);

CREATE INDEX IF NOT EXISTS ix_shadow_signals_observation
    ON end_customer_shadow_identity_signals (observation_id);

CREATE TABLE IF NOT EXISTS end_customer_shadow_fact_proposals (
    proposal_id              VARCHAR(36)  PRIMARY KEY,
    tenant_id                VARCHAR(64)  NOT NULL,
    observation_id           VARCHAR(36)  NOT NULL REFERENCES end_customer_shadow_observations(observation_id) ON DELETE CASCADE,
    field_name               VARCHAR(128) NOT NULL,
    proposed_value           TEXT,
    normalized_value         TEXT,
    confidence               DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    source_type              VARCHAR(32)  NOT NULL DEFAULT 'ai_extraction',
    state                    VARCHAR(32)  NOT NULL,
    target_end_customer_id   VARCHAR(36),
    promotion_status         VARCHAR(32)  NOT NULL DEFAULT 'shadow',
    created_at               TIMESTAMPTZ  NOT NULL,
    promoted_at              TIMESTAMPTZ,
    promoted_by              VARCHAR(128),
    CONSTRAINT uq_shadow_fact_proposal_idempotency
        UNIQUE (tenant_id, observation_id, field_name, normalized_value)
);

CREATE INDEX IF NOT EXISTS ix_shadow_fact_proposals_observation
    ON end_customer_shadow_fact_proposals (observation_id);

CREATE TABLE IF NOT EXISTS end_customer_shadow_match_proposals (
    match_proposal_id        VARCHAR(36)  PRIMARY KEY,
    tenant_id                VARCHAR(64)  NOT NULL,
    observation_id           VARCHAR(36)  NOT NULL REFERENCES end_customer_shadow_observations(observation_id) ON DELETE CASCADE,
    candidate_end_customer_id VARCHAR(36) NOT NULL,
    match_score              DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    match_reasons            JSONB        NOT NULL DEFAULT '[]'::JSONB,
    deterministic_signals    JSONB        NOT NULL DEFAULT '[]'::JSONB,
    ambiguous_signals        JSONB        NOT NULL DEFAULT '[]'::JSONB,
    matcher_version          VARCHAR(32)  NOT NULL DEFAULT 'v1',
    state                    VARCHAR(32)  NOT NULL,
    created_at               TIMESTAMPTZ  NOT NULL,
    resolved_at              TIMESTAMPTZ,
    resolved_by              VARCHAR(128),
    resolution               VARCHAR(64),
    CONSTRAINT uq_shadow_match_proposal_idempotency
        UNIQUE (tenant_id, observation_id, candidate_end_customer_id, matcher_version)
);

CREATE INDEX IF NOT EXISTS ix_shadow_match_proposals_observation
    ON end_customer_shadow_match_proposals (observation_id);
