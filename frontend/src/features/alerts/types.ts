export type AlertSeverity = "info" | "warning" | "high" | "critical"

export type AlertStatus =
  | "open"
  | "acknowledged"
  | "snoozed"
  | "resolved"
  | "suppressed"

export type SeverityBadge = "P1" | "P2" | "P3" | "P4"

export interface AlertFilters {
  status?: AlertStatus | ""
  severity?: AlertSeverity | ""
  tenantId?: string
  alertType?: string
  limit?: number
  offset?: number
}

export interface AlertListItem {
  id: string
  alert_type: string
  alert_type_label: string
  scope_type: string
  tenant_id: string | null
  related_job_id: string | null
  integration_key: string | null
  severity: AlertSeverity
  status: AlertStatus
  title: string
  summary: string
  source_class: string
  first_detected_at: string
  last_detected_at: string
  occurrence_count: number
  age_hours: number | null
  version: number
}

export interface AlertDetail extends AlertListItem {
  safe_details: Record<string, unknown>
  source: string
  source_version: string
  last_evaluated_at: string
  acknowledged_at: string | null
  acknowledged_by: string | null
  snoozed_until: string | null
  resolved_at: string | null
  resolution_reason: string | null
  runbook_ref: string | null
  recommended_action: string | null
}

export interface AlertListResponse {
  generated_at: string
  total: number
  items: AlertListItem[]
  limit: number
  offset: number
}

export interface AlertSummaryResponse {
  generated_at: string
  open_critical: number
  open_high: number
  open_warning: number
  open_info: number
  total_open: number
  last_evaluation_at: string | null
  last_evaluation_status: string | null
}

export interface AlertAcknowledgePayload {
  version: number
  reason?: string
}

export interface AlertResolvePayload {
  version: number
  reason: string
}

export interface AlertWriteResponse {
  alert: AlertDetail
}

export interface OperatorDigestItem {
  priority: number
  kind: string
  title: string
  summary: string
  severity: AlertSeverity | null
  tenant_id: string | null
  alert_id: string | null
  link: string | null
  age_hours: number | null
}

export interface OperatorDigestResponse {
  id: string
  digest_date: string
  timezone: string
  generated_at: string
  period_start: string
  period_end: string
  delivery_status: string
  items: OperatorDigestItem[]
  limitation_notes: string[]
}

export interface OperatorDigestListResponse {
  items: OperatorDigestResponse[]
}
