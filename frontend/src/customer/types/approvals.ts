import type { CustomerStatus } from "@/customer/types/overview"
import type { ListResponse } from "@/customer/types/lists"

export type ApprovalWorkItemType = "lead" | "support" | "unknown"

export type ApprovalListItem = {
  approval_id: string
  work_item_id: string
  work_item_type: ApprovalWorkItemType
  work_item_title: string
  title: string
  summary: string
  customer_status: CustomerStatus
  customer_status_label: string
  requested_at: string
}

export type ApprovalListParams = {
  status: "pending" | "all"
  limit: number
  offset: number
}

export type ApprovalListResponse = ListResponse<ApprovalListItem>
