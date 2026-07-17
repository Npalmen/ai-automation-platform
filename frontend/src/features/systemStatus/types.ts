import type { StatusVariant } from "@/design/types"

export type SystemStatusLevel =
  | "healthy"
  | "warning"
  | "failed"
  | "critical"
  | "paused"
  | "unknown"
  | "not_configured"

export type FreshnessLevel = "reported" | "stale" | "not_reported"

export type VerificationStatus = "success" | "failed" | "not_performed" | "unknown"

export type DomainStatus = {
  status: SystemStatusLevel
  label: string
  summary: string
}

export type ComponentStatus = {
  status: SystemStatusLevel
  label: string
  summary: string
  checked_at: string
  source: string
  freshness?: FreshnessLevel | null
  limitation?: string | null
  details?: Record<string, unknown>
}

export type IntegrationRuntimeStatus = ComponentStatus & {
  issues: number
  affected_tenants: number
}

export type BackupResilienceStatus = ComponentStatus & {
  operation_status?: "success" | "failed" | "unknown" | null
  archive_integrity_verified?: boolean | null
}

export type RestoreResilienceStatus = ComponentStatus & {
  operation_status?: "success" | "failed" | "unknown" | null
  schema_verification?: VerificationStatus | null
  application_smoke_verification?: VerificationStatus | null
}

export type BuildDeployStatus = ComponentStatus & {
  commit_sha?: string | null
  build_time?: string | null
  release_id?: string | null
}

export type LastDeployStatus = ComponentStatus & {
  deployed_at?: string | null
}

export type SystemStatusResponse = {
  generated_at: string
  runtime_status: DomainStatus
  resilience_status: DomainStatus
  deploy_readiness_status: DomainStatus
  overall_status: DomainStatus
  runtime: {
    api: ComponentStatus
    database: ComponentStatus
    scheduler: ComponentStatus
    jobs: ComponentStatus
    integrations: Record<string, IntegrationRuntimeStatus>
  }
  resilience: {
    last_backup: BackupResilienceStatus
    last_restore_test: RestoreResilienceStatus
    retention: ComponentStatus & { retention_days?: number | null }
  }
  deployment: {
    current_build: BuildDeployStatus
    last_deploy: LastDeployStatus
    routing_config: ComponentStatus
    release_gate: ComponentStatus
  }
  limitations: string[]
  runbooks: { id: string; label: string }[]
}

export type StatusVariantForBadge = StatusVariant
