-- Additive idempotency store for operator-controlled end-customer writes.

CREATE TABLE IF NOT EXISTS end_customer_idempotency_records (
    record_id              VARCHAR(36)  PRIMARY KEY,
    tenant_id              VARCHAR(64)  NOT NULL,
    operation_type         VARCHAR(64)  NOT NULL,
    idempotency_key        VARCHAR(128) NOT NULL,
    request_hash           VARCHAR(64)  NOT NULL,
    response_status_code   INTEGER      NOT NULL,
    response_body          JSONB        NOT NULL DEFAULT '{}'::JSONB,
    resource_reference     JSONB        NOT NULL DEFAULT '{}'::JSONB,
    created_at             TIMESTAMPTZ  NOT NULL,
    completed_at           TIMESTAMPTZ  NOT NULL,
    CONSTRAINT uq_end_customer_idempotency_scope
        UNIQUE (tenant_id, operation_type, idempotency_key)
);

CREATE INDEX IF NOT EXISTS ix_end_customer_idempotency_tenant_created
    ON end_customer_idempotency_records (tenant_id, created_at);
