import type { CustomerStatus } from "@/customer/types/overview"
import type { ListResponse } from "@/customer/types/lists"

export type ActivityType = "lead" | "support" | "invoice" | "unknown"

export type ActivityListItem = {
  at: string
  type: ActivityType
  customer_status: CustomerStatus
  customer_status_label: string
  priority: string | null
  label: string
}

export type ActivityListParams = {
  type: "lead" | "support" | "invoice" | "all"
  limit: number
  offset: number
}

export type ActivityListResponse = ListResponse<ActivityListItem>
