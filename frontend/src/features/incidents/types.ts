export type PanelSeverity = "critical" | "failed" | "warning" | "information"

export type IncidentStatus =
  | "open"
  | "acknowledged"
  | "investigating"
  | "monitoring"
  | "resolved"
  | "closed"

export type SeverityBadge = "P1" | "P2" | "P3" | "P4"

export interface IncidentFilters {
  search?: string
  status?: IncidentStatus | ""
  severity?: PanelSeverity | ""
  tenantId?: string
  owner?: string
  sort?: "updated_at" | "created_at" | "severity" | "status" | "title"
  order?: "asc" | "desc"
  limit?: number
  offset?: number
}

export interface IncidentSummary {
  open: number
  investigating: number
  monitoring: number
  resolved: number
  critical: number
  affected_tenants: number
}

export interface IncidentListItem {
  incident_id: string
  title: string
  description: string | null
  severity: PanelSeverity
  severity_badge: SeverityBadge
  status: IncidentStatus
  owner_id: string | null
  owner_display_name: string | null
  tenant_count: number
  signal_count: number
  created_at: string
  updated_at: string
  age_hours: number | null
}

export interface IncidentListResponse {
  generated_at: string
  total: number
  limit: number
  offset: number
  summary: IncidentSummary
  items: IncidentListItem[]
}

export interface IncidentTenantOut {
  tenant_id: string
  tenant_name_snapshot: string | null
  linked_at: string
  unlinked_at: string | null
}

export interface IncidentSignalOut {
  signal_id: string
  tenant_id: string
  source_type: string
  source_id: string
  snapshot_title: string
  snapshot_summary: string
  snapshot_severity: PanelSeverity
  linked_at: string
  unlinked_at: string | null
}

export interface IncidentTimelineEventOut {
  event_id: string
  event_type: string
  actor_id: string
  actor_display_name: string
  actor_role: string
  message: string
  metadata: Record<string, unknown>
  created_at: string
}

export interface AvailableIncidentAction {
  action_id: string
  label: string
  required_role: "read_only" | "operations" | "admin"
  requires_reason: boolean
  requires_confirmation: boolean
  allowed: boolean
  blocked_reason: string | null
}

export interface IncidentDetail {
  incident_id: string
  title: string
  description: string | null
  severity: PanelSeverity
  severity_badge: SeverityBadge
  status: IncidentStatus
  owner_id: string | null
  owner_display_name: string | null
  created_by: string
  created_by_display_name: string
  created_at: string
  updated_at: string
  acknowledged_at: string | null
  resolved_at: string | null
  closed_at: string | null
  resolution_summary: string | null
  version: number
  tenants: IncidentTenantOut[]
  signals: IncidentSignalOut[]
  timeline: IncidentTimelineEventOut[]
  available_actions: AvailableIncidentAction[]
}

export interface IncidentWriteResponse {
  incident_id: string
  version: number
  message: string
  changed: boolean
}

export interface IncidentCreatePayload {
  title: string
  description?: string | null
  severity: PanelSeverity
  tenant_ids?: string[]
  signal_links?: { tenant_id: string; signal_id: string }[]
  reason: string
  confirmation: true
}

export interface IncidentFieldUpdatePayload {
  title?: string
  description?: string | null
  severity?: PanelSeverity
  expected_version: number
  reason: string
  confirmation: true
}

export interface IncidentStatusChangePayload {
  target_status: IncidentStatus
  reason: string
  resolution_summary?: string | null
  expected_version: number
  confirmation: true
}

export interface IncidentAssignSelfPayload {
  expected_version: number
  reason: string
  confirmation: true
}

export interface IncidentNotePayload {
  message: string
  confirmation: true
}

export interface LinkedIncidentSummary {
  incident_id: string
  title: string
  status: IncidentStatus
  severity: PanelSeverity
}

export interface LinkedIncidentsGroup {
  open: LinkedIncidentSummary[]
  closed: LinkedIncidentSummary[]
}

export interface RecommendedIncidentAction {
  action: "create_from_signal"
  tenant_id: string
  signal_id: string
  prefill_title: string
  prefill_severity: PanelSeverity
}
