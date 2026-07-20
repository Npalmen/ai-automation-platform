import type { PriorityItem } from "@/features/overview/types"
import type { StatusVariant } from "@/design/types"
import type { AvailableActionMeta } from "@/features/operatorActions/types"

export type IntegrationSummaryStatus = "healthy" | "warning" | "failed" | "unknown"
export type TenantStatusValue = "active" | "inactive" | "unknown"

export type TenantHealth = {
  level: StatusVariant
  label: string
  summary: string
}

export type IntegrationSummary = {
  google_mail: IntegrationSummaryStatus
  visma: IntegrationSummaryStatus
  google_sheets: IntegrationSummaryStatus
}

export type TenantListItem = {
  tenant_id: string
  name: string
  slug: string | null
  tenant_status: TenantStatusValue
  health: TenantHealth
  package: null
  operator_owner: null
  enabled_modules: string[]
  open_issues_count: number
  pending_approvals: number
  open_manual_reviews: number
  jobs_last_30d: number
  last_activity_at: string | null
  integrations_summary: IntegrationSummary
  created_at: string | null
  updated_at: string | null
}

export type TenantListResponse = {
  items: TenantListItem[]
  total: number
}

export type TenantBasicInfo = {
  tenant_id: string
  name: string
  slug: string | null
  tenant_status: TenantStatusValue
  package: null
  operator_owner: null
  enabled_modules: string[]
  enabled_job_types: string[]
  allowed_integrations: string[]
  auto_actions: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
}

export type TenantIntegrationStatus = {
  status: IntegrationSummaryStatus
  description: string
  recommended_action: string | null
  data_source: string
  last_success_at: string | null
  last_error_at: string | null
}

export type TenantIntegrationsBlock = {
  google_mail: TenantIntegrationStatus | null
  monday: TenantIntegrationStatus | null
  fortnox: TenantIntegrationStatus | null
  visma: TenantIntegrationStatus
  google_sheets: TenantIntegrationStatus
}

export type TenantJobSummary = {
  job_id: string
  job_type: string
  status: string
  created_at: string
  updated_at: string
}

export type TenantJobsBlock = {
  total: number
  jobs_last_30d: number
  recent: TenantJobSummary[]
}

export type TenantApprovalSummary = {
  approval_id: string
  job_id: string
  job_type: string
  state: string
  title: string | null
  summary: string | null
  created_at: string
}

export type TenantApprovalsBlock = {
  pending_count: number
  recent: TenantApprovalSummary[]
}

export type TenantManualReviewItem = {
  job_id: string
  job_type: string
  status: string
  subject: string | null
  manual_review_reason: string | null
  unresolved: boolean
}

export type TenantManualReviewBlock = {
  total: number
  recent: TenantManualReviewItem[]
}

export type TenantUsageBlock = {
  jobs_created: number
  jobs_completed: number
  pending_approvals: number
  blocked_flows: number
  dispatches_total: number
  dispatches_successful: number
  dispatches_failed: number
  automation_rate_percent: number
  time_saved_hours: number
}

export type TenantAuditEvent = {
  event_id: string
  tenant_id: string
  category: string
  action: string
  status: string
  details: Record<string, unknown>
  created_at: string
}

export type TenantAuditBlock = {
  total: number
  recent: TenantAuditEvent[]
}

export type TenantLifecycleSummary = {
  tenant_id: string
  lifecycle_status: string
  lifecycle_label_sv: string
  config_version: number
  is_test_tenant: boolean
  operations_paused: boolean
  scheduler_run_mode: string | null
  lifecycle_updated_at: string | null
  lifecycle_updated_by: string | null
  last_config_updated_by: string | null
}

export type TenantOnboardingConfigSummary = {
  schema_version: number | null
  service_profiles: string[]
  lead_requirements: Record<string, { required?: string[]; optional?: string[] }>
  internal_routing_hints: Record<string, string>
  intake: {
    mode?: string | null
    activation_cutoff_at?: string | null
    enforcement?: string | null
  }
}

export type TenantDetailResponse = {
  tenant: TenantBasicInfo
  health: TenantHealth
  integrations: TenantIntegrationsBlock
  jobs: TenantJobsBlock
  approvals: TenantApprovalsBlock
  manual_review: TenantManualReviewBlock
  recent_errors: PriorityItem[]
  usage: TenantUsageBlock
  audit: TenantAuditBlock
  onboarding_config: TenantOnboardingConfigSummary
  lifecycle?: TenantLifecycleSummary | null
  available_actions: AvailableActionMeta[]
}

export type TenantListFilters = {
  search?: string
  status?: TenantStatusValue | ""
  health?: StatusVariant | ""
  sort?: "name" | "tenant_status" | "health" | "last_activity" | "open_issues"
  order?: "asc" | "desc"
}
