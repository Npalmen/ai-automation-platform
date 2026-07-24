-- Kapitel 2F.3B.2: permanent LLM operation idempotency and snapshot call budget

ALTER TABLE live_eval_runs
    ADD COLUMN IF NOT EXISTS llm_max_calls INTEGER;

CREATE TABLE IF NOT EXISTS live_eval_llm_operations (
    id                       BIGSERIAL PRIMARY KEY,
    tenant_id                VARCHAR(64)  NOT NULL,
    evaluation_run_id        VARCHAR(36)  NOT NULL,
    scenario_id              VARCHAR(128) NOT NULL,
    prompt_name              VARCHAR(64)  NOT NULL,
    request_ordinal          INTEGER      NOT NULL,
    operation_key            VARCHAR(200) NOT NULL,
    prompt_version           VARCHAR(32),
    llm_provider             VARCHAR(64)  NOT NULL,
    requested_model          VARCHAR(128) NOT NULL,
    returned_model           VARCHAR(128),
    status                   VARCHAR(32)  NOT NULL,
    provider_started_at      TIMESTAMPTZ,
    completed_at             TIMESTAMPTZ,
    latency_ms               INTEGER,
    input_tokens             INTEGER,
    output_tokens            INTEGER,
    total_tokens             INTEGER,
    finish_reason            VARCHAR(64),
    schema_validation_status VARCHAR(32),
    output_hash              VARCHAR(64),
    failure_reason           VARCHAR(128),
    created_at               TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_live_eval_llm_operations_run
        FOREIGN KEY (tenant_id, evaluation_run_id)
        REFERENCES live_eval_runs (tenant_id, evaluation_run_id),
    CONSTRAINT uq_live_eval_llm_operations_operation_key UNIQUE (operation_key),
    CONSTRAINT uq_live_eval_llm_operations_run_prompt UNIQUE (evaluation_run_id, prompt_name),
    CONSTRAINT uq_live_eval_llm_operations_run_ordinal UNIQUE (evaluation_run_id, request_ordinal),
    CONSTRAINT ck_live_eval_llm_operations_ordinal CHECK (request_ordinal BETWEEN 1 AND 4)
);

CREATE INDEX IF NOT EXISTS ix_live_eval_llm_operations_run
    ON live_eval_llm_operations (evaluation_run_id, request_ordinal);

CREATE INDEX IF NOT EXISTS ix_live_eval_llm_operations_tenant
    ON live_eval_llm_operations (tenant_id, evaluation_run_id);
