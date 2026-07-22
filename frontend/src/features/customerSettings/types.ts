export type SettingsDomain =
  | "identity"
  | "modules"
  | "services"
  | "integrations"
  | "routing"
  | "automation"
  | "intake"
  | "readiness"

export type SettingsTab = SettingsDomain

export type DomainPermissions = {
  read: boolean
  write: boolean
  preview: boolean
}

export type ReadinessBlocker = {
  code: string
  domain: string
  message: string
  action_domain: string
  affected_capabilities: string[]
}

export type ReadinessWarning = {
  code: string
  domain: string
  message: string
  action_domain: string
}

export type EffectiveReadiness = {
  overall_status: string
  is_stale: boolean
  stale_domains: string[]
  blockers: ReadinessBlocker[]
  warnings: ReadinessWarning[]
  integration_group_status: {
    groups: Array<{
      group_key: string
      satisfied: boolean
      implementation: string
      reason: string
    }>
    finance_destination: Record<string, unknown>
  }
  affected_capabilities: string[]
}

export type CustomerSettingsAggregate = {
  tenant_id: string
  tenant_status: string
  lifecycle_status: string
  config_version: number
  domains: Record<string, Record<string, unknown>>
  effective_capabilities: Array<{
    key: string
    label_sv: string
    enabled_job_types: string[]
  }>
  integration_selection_view: Array<{
    integration_key: string
    display_name_sv: string
    selection_status: string
    support_status: string | null
    selectable: boolean
    migration_review_required: boolean
    requirement_source: string
  }>
  integration_group_status: EffectiveReadiness["integration_group_status"]
  routing_summary: {
    routing: Record<string, unknown>
    internal_routing_hints: Record<string, unknown>
  }
  automation_policy_summary: {
    automation: Record<string, unknown>
    scheduler_run_mode: string | null
    operations_paused: boolean
    auto_actions: Record<string, string>
    enabled_external_writes: string[]
  }
  readiness_summary: {
    stale: boolean
    config_version: number
    readiness_config_version: number | null
    readiness_checked_at: string | null
  }
  effective_readiness: EffectiveReadiness
  permissions: Record<string, DomainPermissions>
  last_updated: {
    at: string | null
    by: string | null
  }
}

export type CustomerSettingsPatchRequest = {
  expected_config_version: number
  change_reason?: string | null
  payload: Record<string, unknown>
}

export type CustomerSettingsPatchResponse = {
  tenant_id: string
  section: string
  config_version: number
  payload: Record<string, unknown>
}

export type CustomerSettingsPreviewResponse = {
  tenant_id: string
  domain: string
  config_version: number
  valid: boolean
  warnings: string[]
  blocking: string[]
  readiness_domains_affected: string[]
  runtime_gates: Record<string, unknown>
  credential_preservation: boolean
  normalized_payload: Record<string, unknown>
  preview_fingerprint: string
  finance_destination?: Record<string, unknown> | null
  automation_projection?: {
    auto_actions: Record<string, string>
    automation_flags?: Record<string, boolean>
  } | null
}

export type ConflictState = {
  serverConfigVersion: number
  message: string
}
