import type { SeverityVariant } from "@/design/types"
import type { AvailableActionMeta } from "@/features/operatorActions/types"

export type PanelSeverity = "critical" | "failed" | "warning" | "information"
export type SignalState = "yes" | "no" | "unknown" | "not_applicable"

export type RunbookRef = {
  id: string
  label: string
}

export type NeedsHelpQueueItem = {
  id: string
  tenant_id: string
  customer_name: string
  category: string
  title: string
  impact: string
  severity: PanelSeverity
  severity_badge: SeverityVariant
  detected_at: string | null
  age_hours: number | null
  recommended_action: string
  safe_retry_available: SignalState
  external_action_may_have_occurred: SignalState
  link: string
  source_type: string
  available_actions: AvailableActionMeta[]
}

export type NeedsHelpSummary = {
  critical: number
  failed: number
  warning: number
  information: number
  affected_tenants: number
  safe_retry_yes: number
  external_action_yes_or_unknown: number
}

export type NeedsHelpQueueResponse = {
  generated_at: string
  total: number
  summary: NeedsHelpSummary
  items: NeedsHelpQueueItem[]
  limit: number
  offset: number
}

export type NeedsHelpItemDetail = NeedsHelpQueueItem & {
  runbook: RunbookRef | null
  recommended_incident_action?: RecommendedIncidentAction | null
  linked_incidents?: LinkedIncidentsGroup
}

export type LinkedIncidentSummary = {
  incident_id: string
  title: string
  status: string
  severity: PanelSeverity
}

export type LinkedIncidentsGroup = {
  open: LinkedIncidentSummary[]
  closed: LinkedIncidentSummary[]
}

export type RecommendedIncidentAction = {
  action: "create_from_signal"
  tenant_id: string
  signal_id: string
  prefill_title: string
  prefill_severity: PanelSeverity
}

export type NeedsHelpFilters = {
  search?: string
  severity?: PanelSeverity | ""
  category?: string
  tenantId?: string
  sourceType?: string
  safeRetry?: SignalState | ""
  externalImpact?: SignalState | ""
  minimumAgeHours?: number
  sort?: "priority" | "age" | "tenant" | "severity"
  order?: "asc" | "desc"
  limit?: number
  offset?: number
}
