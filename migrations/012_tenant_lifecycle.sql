-- Onboarding 2.0: tenant lifecycle columns (additive)
ALTER TABLE tenant_configs ADD COLUMN IF NOT EXISTS lifecycle_status VARCHAR(32) NOT NULL DEFAULT 'onboarding';
ALTER TABLE tenant_configs ADD COLUMN IF NOT EXISTS config_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE tenant_configs ADD COLUMN IF NOT EXISTS lifecycle_updated_at TIMESTAMPTZ;
ALTER TABLE tenant_configs ADD COLUMN IF NOT EXISTS lifecycle_updated_by VARCHAR(128);
ALTER TABLE tenant_configs ADD COLUMN IF NOT EXISTS is_test_tenant BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE tenant_configs ADD COLUMN IF NOT EXISTS last_config_updated_by VARCHAR(128);
ALTER TABLE tenant_configs ADD COLUMN IF NOT EXISTS readiness_config_version INTEGER;
ALTER TABLE tenant_configs ADD COLUMN IF NOT EXISTS readiness_checked_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_tenant_configs_lifecycle_status ON tenant_configs (lifecycle_status);

-- Existing active tenants: set lifecycle to active
UPDATE tenant_configs SET lifecycle_status = 'active' WHERE status = 'active' AND lifecycle_status = 'onboarding';
UPDATE tenant_configs SET lifecycle_status = 'onboarding' WHERE status = 'inactive' AND lifecycle_status = 'onboarding';
