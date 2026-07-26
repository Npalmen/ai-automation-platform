-- Customer Domain Foundation: tenant-isolated end-customer persistence (10 tables).
-- Additive only — no changes to jobs, Gmail, approvals, or action tables.

CREATE TABLE IF NOT EXISTS end_customer_companies (
    company_id   VARCHAR(36)  PRIMARY KEY,
    tenant_id    VARCHAR(64)  NOT NULL,
    legal_name   VARCHAR(512) NOT NULL,
    display_name VARCHAR(512) NOT NULL,
    status       VARCHAR(32)  NOT NULL,
    created_at   TIMESTAMPTZ  NOT NULL,
    updated_at   TIMESTAMPTZ  NOT NULL,
    CONSTRAINT uq_end_customer_companies_tenant_company UNIQUE (tenant_id, company_id)
);

CREATE INDEX IF NOT EXISTS ix_end_customer_companies_tenant_status
    ON end_customer_companies (tenant_id, status);

CREATE TABLE IF NOT EXISTS end_customer_contacts (
    contact_id   VARCHAR(36)  PRIMARY KEY,
    tenant_id    VARCHAR(64)  NOT NULL,
    given_name   VARCHAR(256),
    family_name  VARCHAR(256),
    display_name VARCHAR(512) NOT NULL,
    title        VARCHAR(256),
    status       VARCHAR(32)  NOT NULL,
    created_at   TIMESTAMPTZ  NOT NULL,
    updated_at   TIMESTAMPTZ  NOT NULL,
    CONSTRAINT uq_end_customer_contacts_tenant_contact UNIQUE (tenant_id, contact_id)
);

CREATE INDEX IF NOT EXISTS ix_end_customer_contacts_tenant_status
    ON end_customer_contacts (tenant_id, status);

CREATE TABLE IF NOT EXISTS end_customers (
    customer_id         VARCHAR(36)  PRIMARY KEY,
    tenant_id           VARCHAR(64)  NOT NULL,
    customer_type       VARCHAR(32)  NOT NULL,
    status              VARCHAR(32)  NOT NULL,
    display_name        VARCHAR(512) NOT NULL,
    primary_company_id  VARCHAR(36),
    primary_contact_id  VARCHAR(36),
    version             INTEGER      NOT NULL DEFAULT 1,
    created_at          TIMESTAMPTZ  NOT NULL,
    updated_at          TIMESTAMPTZ  NOT NULL,
    CONSTRAINT uq_end_customers_tenant_customer UNIQUE (tenant_id, customer_id),
    CONSTRAINT ck_end_customers_version CHECK (version >= 1),
    CONSTRAINT fk_end_customers_primary_company
        FOREIGN KEY (tenant_id, primary_company_id)
        REFERENCES end_customer_companies (tenant_id, company_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_end_customers_primary_contact
        FOREIGN KEY (tenant_id, primary_contact_id)
        REFERENCES end_customer_contacts (tenant_id, contact_id)
        ON DELETE NO ACTION
);

CREATE INDEX IF NOT EXISTS ix_end_customers_tenant_status
    ON end_customers (tenant_id, status);

CREATE TABLE IF NOT EXISTS end_customer_source_facts (
    fact_id                 VARCHAR(36)  PRIMARY KEY,
    tenant_id               VARCHAR(64)  NOT NULL,
    subject_type            VARCHAR(32)  NOT NULL,
    subject_id              VARCHAR(36)  NOT NULL,
    field_name              VARCHAR(128) NOT NULL,
    raw_value               TEXT,
    normalized_value        TEXT,
    fact_state              VARCHAR(32)  NOT NULL,
    source_type             VARCHAR(32)  NOT NULL,
    source_reference        JSONB,
    source_actor            VARCHAR(128),
    confidence              DOUBLE PRECISION NOT NULL,
    observed_at             TIMESTAMPTZ,
    recorded_at             TIMESTAMPTZ  NOT NULL,
    verified_at             TIMESTAMPTZ,
    verified_by             VARCHAR(128),
    supersedes_fact_id      VARCHAR(36),
    conflicts_with_fact_ids JSONB        NOT NULL DEFAULT '[]'::JSONB,
    CONSTRAINT uq_end_customer_source_facts_tenant_fact UNIQUE (tenant_id, fact_id),
    CONSTRAINT ck_end_customer_source_facts_confidence CHECK (confidence >= 0.0 AND confidence <= 1.0),
    CONSTRAINT fk_end_customer_source_facts_supersedes
        FOREIGN KEY (tenant_id, supersedes_fact_id)
        REFERENCES end_customer_source_facts (tenant_id, fact_id)
        ON DELETE NO ACTION
);

CREATE INDEX IF NOT EXISTS ix_end_customer_source_facts_subject
    ON end_customer_source_facts (tenant_id, subject_type, subject_id, recorded_at);

CREATE TABLE IF NOT EXISTS end_customer_identities (
    identity_id        VARCHAR(36)  PRIMARY KEY,
    tenant_id          VARCHAR(64)  NOT NULL,
    owner_type         VARCHAR(32)  NOT NULL,
    owner_id           VARCHAR(36)  NOT NULL,
    identity_type      VARCHAR(32)  NOT NULL,
    raw_value          TEXT         NOT NULL,
    normalized_value   TEXT,
    fact_state         VARCHAR(32)  NOT NULL,
    verification_status VARCHAR(32) NOT NULL,
    source_fact_id     VARCHAR(36),
    first_seen_at      TIMESTAMPTZ,
    last_seen_at       TIMESTAMPTZ,
    CONSTRAINT uq_end_customer_identities_tenant_identity UNIQUE (tenant_id, identity_id),
    CONSTRAINT fk_end_customer_identities_source_fact
        FOREIGN KEY (tenant_id, source_fact_id)
        REFERENCES end_customer_source_facts (tenant_id, fact_id)
        ON DELETE NO ACTION
);

CREATE INDEX IF NOT EXISTS ix_end_customer_identities_candidate
    ON end_customer_identities (tenant_id, identity_type, normalized_value);

CREATE UNIQUE INDEX IF NOT EXISTS uq_end_customer_identities_owner_normalized
    ON end_customer_identities (tenant_id, owner_type, owner_id, identity_type, normalized_value)
    WHERE normalized_value IS NOT NULL;

CREATE TABLE IF NOT EXISTS end_customer_relationships (
    relationship_id   VARCHAR(36)  PRIMARY KEY,
    tenant_id         VARCHAR(64)  NOT NULL,
    customer_id       VARCHAR(36)  NOT NULL,
    subject_type      VARCHAR(32)  NOT NULL,
    subject_id        VARCHAR(36)  NOT NULL,
    relationship_type VARCHAR(32)  NOT NULL,
    is_primary        BOOLEAN      NOT NULL DEFAULT FALSE,
    valid_from        TIMESTAMPTZ,
    valid_to          TIMESTAMPTZ,
    CONSTRAINT uq_end_customer_relationships_tenant_rel UNIQUE (tenant_id, relationship_id),
    CONSTRAINT fk_end_customer_relationships_customer
        FOREIGN KEY (tenant_id, customer_id)
        REFERENCES end_customers (tenant_id, customer_id)
        ON DELETE NO ACTION
);

CREATE INDEX IF NOT EXISTS ix_end_customer_relationships_customer
    ON end_customer_relationships (tenant_id, customer_id);

CREATE TABLE IF NOT EXISTS end_customer_job_links (
    link_id      VARCHAR(36)  PRIMARY KEY,
    tenant_id    VARCHAR(64)  NOT NULL,
    customer_id  VARCHAR(36)  NOT NULL,
    job_id       VARCHAR(64)  NOT NULL,
    link_type    VARCHAR(32)  NOT NULL,
    confidence   DOUBLE PRECISION NOT NULL,
    source_type  VARCHAR(32)  NOT NULL,
    created_at   TIMESTAMPTZ  NOT NULL,
    created_by   VARCHAR(128),
    CONSTRAINT uq_end_customer_job_links_tenant_link UNIQUE (tenant_id, link_id),
    CONSTRAINT uq_end_customer_job_links_idempotency
        UNIQUE (tenant_id, customer_id, job_id, link_type),
    CONSTRAINT ck_end_customer_job_links_confidence
        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    CONSTRAINT fk_end_customer_job_links_customer
        FOREIGN KEY (tenant_id, customer_id)
        REFERENCES end_customers (tenant_id, customer_id)
        ON DELETE NO ACTION
);

CREATE INDEX IF NOT EXISTS ix_end_customer_job_links_job
    ON end_customer_job_links (tenant_id, job_id);

CREATE TABLE IF NOT EXISTS end_customer_thread_links (
    link_id                       VARCHAR(36)  PRIMARY KEY,
    tenant_id                     VARCHAR(64)  NOT NULL,
    customer_id                   VARCHAR(36)  NOT NULL,
    integration_type              VARCHAR(64)  NOT NULL,
    integration_account_reference VARCHAR(256) NOT NULL,
    thread_id                     VARCHAR(320) NOT NULL,
    link_type                     VARCHAR(32)  NOT NULL,
    confidence                    DOUBLE PRECISION NOT NULL,
    source_type                   VARCHAR(32)  NOT NULL,
    created_at                    TIMESTAMPTZ  NOT NULL,
    CONSTRAINT uq_end_customer_thread_links_tenant_link UNIQUE (tenant_id, link_id),
    CONSTRAINT uq_end_customer_thread_links_idempotency
        UNIQUE (tenant_id, customer_id, integration_type, integration_account_reference, thread_id, link_type),
    CONSTRAINT ck_end_customer_thread_links_confidence
        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    CONSTRAINT fk_end_customer_thread_links_customer
        FOREIGN KEY (tenant_id, customer_id)
        REFERENCES end_customers (tenant_id, customer_id)
        ON DELETE NO ACTION
);

CREATE INDEX IF NOT EXISTS ix_end_customer_thread_links_context
    ON end_customer_thread_links (tenant_id, integration_type, integration_account_reference, thread_id);

CREATE TABLE IF NOT EXISTS end_customer_timeline_events (
    timeline_event_id   VARCHAR(36)  PRIMARY KEY,
    tenant_id           VARCHAR(64)  NOT NULL,
    customer_id         VARCHAR(36)  NOT NULL,
    event_type          VARCHAR(64)  NOT NULL,
    occurred_at         TIMESTAMPTZ  NOT NULL,
    recorded_at         TIMESTAMPTZ  NOT NULL,
    actor_type          VARCHAR(32),
    actor_id            VARCHAR(128),
    source_type         VARCHAR(32),
    reference_type      VARCHAR(32),
    reference_id        VARCHAR(320),
    summary             TEXT         NOT NULL,
    metadata            JSONB        NOT NULL DEFAULT '{}'::JSONB,
    replay_identity_key VARCHAR(512) NOT NULL,
    CONSTRAINT uq_end_customer_timeline_events_tenant_event UNIQUE (tenant_id, timeline_event_id),
    CONSTRAINT uq_end_customer_timeline_events_replay
        UNIQUE (tenant_id, replay_identity_key),
    CONSTRAINT fk_end_customer_timeline_events_customer
        FOREIGN KEY (tenant_id, customer_id)
        REFERENCES end_customers (tenant_id, customer_id)
        ON DELETE NO ACTION
);

CREATE INDEX IF NOT EXISTS ix_end_customer_timeline_events_order
    ON end_customer_timeline_events (tenant_id, customer_id, occurred_at, recorded_at, timeline_event_id);

CREATE TABLE IF NOT EXISTS end_customer_duplicate_candidates (
    candidate_id       VARCHAR(36)  PRIMARY KEY,
    tenant_id          VARCHAR(64)  NOT NULL,
    left_customer_id   VARCHAR(36)  NOT NULL,
    right_customer_id  VARCHAR(36)  NOT NULL,
    status             VARCHAR(32)  NOT NULL,
    confidence         DOUBLE PRECISION NOT NULL,
    evidence           JSONB        NOT NULL DEFAULT '[]'::JSONB,
    conflicts          JSONB        NOT NULL DEFAULT '[]'::JSONB,
    version            INTEGER      NOT NULL DEFAULT 1,
    created_at         TIMESTAMPTZ  NOT NULL,
    updated_at         TIMESTAMPTZ  NOT NULL,
    CONSTRAINT uq_end_customer_duplicate_candidates_tenant_candidate
        UNIQUE (tenant_id, candidate_id),
    CONSTRAINT uq_end_customer_duplicate_candidates_pair
        UNIQUE (tenant_id, left_customer_id, right_customer_id),
    CONSTRAINT ck_end_customer_duplicate_candidates_version CHECK (version >= 1),
    CONSTRAINT ck_end_customer_duplicate_candidates_confidence
        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    CONSTRAINT ck_end_customer_duplicate_candidates_pair_order
        CHECK (left_customer_id < right_customer_id),
    CONSTRAINT ck_end_customer_duplicate_candidates_pair_distinct
        CHECK (left_customer_id <> right_customer_id),
    CONSTRAINT fk_end_customer_duplicate_candidates_left
        FOREIGN KEY (tenant_id, left_customer_id)
        REFERENCES end_customers (tenant_id, customer_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_end_customer_duplicate_candidates_right
        FOREIGN KEY (tenant_id, right_customer_id)
        REFERENCES end_customers (tenant_id, customer_id)
        ON DELETE NO ACTION
);

CREATE INDEX IF NOT EXISTS ix_end_customer_duplicate_candidates_status
    ON end_customer_duplicate_candidates (tenant_id, status);
