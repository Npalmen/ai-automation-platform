import type { SeverityVariant, StatusVariant } from "@/design/types"

export type TriState = "yes" | "no" | "unknown"

export type CounterValue = {
  value: number
  window_hours: number | null
}

export type PeriodInfo = {
  hours: number
  started_at: string
}

export type PlatformStatus = {
  level: StatusVariant
  label: string
  summary: string
}

export type Counters = {
  active_tenants: CounterValue
  jobs_last_24h: CounterValue
  pending_approvals: CounterValue
  open_manual_reviews: CounterValue
  failed_jobs: CounterValue
  stuck_jobs: CounterValue
  integration_errors: CounterValue
}

export type IntegrationStatus = {
  status: StatusVariant
  issues: number
  affected_tenants: number
  data_source: string
}

export type IntegrationsBlock = {
  gmail: IntegrationStatus
  visma: IntegrationStatus
  google_sheets: IntegrationStatus
}

export type SystemComponentStatus = {
  status: StatusVariant
  description?: string | null
}

export type BackupStatus = {
  status: StatusVariant
  data_source: string
}

export type DeployStatus = {
  status: StatusVariant
  data_source: string
}

export type SystemBlock = {
  api: SystemComponentStatus
  database: SystemComponentStatus
  scheduler: SystemComponentStatus
  backup: BackupStatus
  deploy: DeployStatus
}

export type PriorityItem = {
  id: string
  tenant_id: string
  customer_name: string
  category: string
  title: string
  impact: string
  severity: string
  severity_badge: SeverityVariant
  detected_at: string | null
  age_hours: number | null
  recommended_action: string
  safe_retry_available: TriState
  external_action_may_have_occurred: TriState
  link: string
}

export type OperationsOverviewResponse = {
  generated_at: string
  period: PeriodInfo
  platform_status: PlatformStatus
  counters: Counters
  integrations: IntegrationsBlock
  system: SystemBlock
  priorities: PriorityItem[]
}
