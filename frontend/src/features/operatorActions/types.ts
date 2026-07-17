export type SafetyClass = "safe_write" | "critical_write"

export type AvailableActionMeta = {
  action_id: string
  label: string
  safety_class: SafetyClass
  required_role: "read_only" | "operations" | "admin"
  requires_reason: boolean
  requires_confirmation: boolean
  allowed: boolean
  blocked_reason: string | null
}

export type OperatorActionRequest = {
  reason: string
  confirmation: true
  idempotency_key?: string | null
}

export type OperatorActionStatus =
  | "completed"
  | "no_change"
  | "blocked"
  | "failed"
  | "uncertain"

export type OperatorActionResponse = {
  action_id: string
  tenant_id: string
  resource_id: string | null
  status: OperatorActionStatus
  changed: boolean
  message: string
  executed_at: string
  audit_event_id: string | null
}

export type OperatorActionContext = {
  tenantId: string
  approvalId?: string
}
