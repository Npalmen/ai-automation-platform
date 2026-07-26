import type { CustomerStatus } from "@/customer/types/overview"
import type { ListResponse } from "@/customer/types/lists"

export type WorkItemType = "lead" | "support" | "needs_help" | "unknown"

export type WorkItemListItem = {
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
}

export type WorkItemListParams = {
  type: "lead" | "support" | "needs_help" | "all"
  status?: CustomerStatus
  sort?: "updated_at" | "priority_rank" | "created_at"
  order?: "asc" | "desc"
  q?: string
  from?: string
  to?: string
  limit: number
  offset: number
}

export type WorkItemListResponse = ListResponse<WorkItemListItem>
