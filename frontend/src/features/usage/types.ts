import type { StatusVariant } from "@/design/types"

export type UsageDays = 7 | 30 | 90

export interface UsagePeriod {
  days: number
  started_at: string
  ended_at: string
  comparison_started_at: string
  comparison_ended_at: string
}

export interface ComparisonInt {
  current: number
  previous: number
  absolute_change: number
  percentage_change: number | null
}

export interface ProxyTimestampMetric {
  value: number
  timestamp_basis: "updated_at_proxy"
}

export interface ComparisonProxyMetric {
  current: ProxyTimestampMetric
  previous: ProxyTimestampMetric
  absolute_change: number
  percentage_change: number | null
}

export interface NotMeasuredValue {
  value: null
  status: "not_measured"
  reason: string
}

export interface AiUsageBlock {
  status: "measured" | "not_measured"
  input_tokens?: number | null
  output_tokens?: number | null
  requests?: number | null
  reason?: string | null
}

export interface AiCostBlock {
  status: "measured" | "estimated" | "unknown"
  amount: number | null
  currency?: string | null
  calculation_method?: string | null
  pricing_version?: string | null
  reason?: string | null
}

export interface CapacityBlock {
  status: "measured" | "baseline_missing" | "warning" | "unknown"
  jobs_per_day_average?: number | null
  peak_jobs_per_hour?: number | null
  operator_actions_per_day?: number | null
  open_incidents_current?: number | null
  needs_help_open_current?: number | null
}

export interface UsageSummary {
  active_tenants: number
  tenants_with_activity: number
  jobs_received: ComparisonInt
  jobs_completed: ComparisonProxyMetric
  jobs_failed: ComparisonProxyMetric
  automation_rate: NotMeasuredValue
  operator_actions: ComparisonInt
  gmail_manual_review_handoffs: ComparisonInt
  manual_reviews_created: NotMeasuredValue
  open_manual_reviews_current: number
  pending_approvals_current: number
  incidents_created: ComparisonInt
  incidents_resolved: ComparisonInt
  open_incidents_current: number
  critical_incidents_created: ComparisonInt
  integration_errors: ComparisonInt
  needs_help_open_current: number
  tenants_with_open_signals_current: number
}

export interface UsageOverviewResponse {
  generated_at: string
  period: UsagePeriod
  summary: UsageSummary
  ai_usage: AiUsageBlock
  ai_cost: AiCostBlock
  capacity: CapacityBlock
  data_quality_notes: string[]
}

export interface UsageTenantItem {
  tenant_id: string
  customer_name: string
  tenant_status: string
  jobs_received: number
  jobs_completed: ProxyTimestampMetric
  jobs_failed: ProxyTimestampMetric
  automation_rate: NotMeasuredValue
  gmail_manual_review_handoffs: number
  manual_reviews_created: NotMeasuredValue
  open_manual_reviews_current: number
  pending_approvals_current: number
  operator_actions: number
  incidents_created: number
  integration_errors: number
  ai_usage: AiUsageBlock
  ai_cost: AiCostBlock
  latest_activity_at: string | null
  attention_status: StatusVariant
}

export interface UsageTenantListResponse {
  generated_at: string
  period: UsagePeriod
  total: number
  limit: number
  offset: number
  items: UsageTenantItem[]
}

export type UsageTenantSort =
  | "jobs"
  | "operator_actions"
  | "manual_reviews"
  | "integration_errors"
  | "latest_activity"
  | "customer"

export interface UsageTenantFilters {
  days?: UsageDays
  search?: string
  tenantStatus?: string
  attentionStatus?: string
  minimumJobs?: number
  hasOperatorBurden?: boolean
  sort?: UsageTenantSort
  order?: "asc" | "desc"
  limit?: number
  offset?: number
}
