export type CustomerStatus =
  | "new"
  | "prioritized"
  | "in_progress"
  | "waiting_for_decision"
  | "waiting_for_customer"
  | "prepared"
  | "scheduled"
  | "completed"
  | "needs_help"
  | "failed"
  | "cancelled"
  | "unknown"

export type OverviewSummary = {
  cases_handled_today: number
  waiting_for_decision: number
  waiting_for_customer: number
  needs_help: number
  failed_today: number
  estimated_hours_saved?: number
  estimated_value_sek?: number
}

export type PriorityWorkItemType =
  | "lead"
  | "support"
  | "approval"
  | "needs_help"
  | "unknown"

export type PriorityWorkItem = {
  work_item_id: string
  type: PriorityWorkItemType
  title: string
  customer_name: string | null
  customer_status: CustomerStatus
  customer_status_label: string
  priority_rank: number
  priority_label: string | null
  updated_at: string
}

export type PartialError = {
  section: string
  code: string
  message: string
}

export type WorkspaceOverview = {
  last_updated_at: string
  summary: OverviewSummary
  priority_work_items: PriorityWorkItem[]
  partial_errors: PartialError[]
}
