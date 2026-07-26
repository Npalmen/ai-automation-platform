import type { CustomerStatus } from "@/customer/types/overview"
import type { WorkItemType } from "@/customer/types/work-items"

export type WorkItemTimelineKind =
  | "received"
  | "prepared"
  | "waiting_for_decision"
  | "waiting_for_customer"
  | "system_action"
  | "completed"
  | "failed"
  | "human_takeover"
  | "unknown"

export type WorkItemTimelineItem = {
  at: string
  kind: WorkItemTimelineKind
  label: string
  detail: string | null
}

export type WorkItemDetail = {
  work_item_id: string
  type: WorkItemType
  title: string
  customer_name: string | null
  customer_email: string | null
  customer_status: CustomerStatus
  customer_status_label: string
  priority_rank: number
  priority_label: string | null
  summary: string
  created_at: string
  updated_at: string
  timeline: WorkItemTimelineItem[]
  waiting_for: string | null
  human_takeover_required: boolean
}
