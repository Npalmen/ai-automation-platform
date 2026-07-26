import type { CustomerStatus } from "@/customer/types/overview"

export const WORK_QUEUE_PAGE_SIZE = 10

export type WorkQueueSortKey = "priority_rank" | "updated_at" | "created_at"

export type WorkQueueSortOption = {
  id: string
  label: string
  sort: WorkQueueSortKey
  order: "asc" | "desc"
}

export const WORK_QUEUE_SORT_OPTIONS: WorkQueueSortOption[] = [
  { id: "priority", label: "Prioritet", sort: "priority_rank", order: "asc" },
  { id: "updated", label: "Senast uppdaterad", sort: "updated_at", order: "desc" },
  { id: "newest", label: "Nyast", sort: "created_at", order: "desc" },
  { id: "oldest", label: "Äldst", sort: "created_at", order: "asc" },
]

export type StatusFilterOption = {
  value: CustomerStatus | "all"
  label: string
}

export const WORK_QUEUE_STATUS_FILTERS: StatusFilterOption[] = [
  { value: "all", label: "Alla" },
  { value: "new", label: "Nya" },
  { value: "prioritized", label: "Prioriterade" },
  { value: "in_progress", label: "Pågår" },
  { value: "waiting_for_decision", label: "Väntar på beslut" },
  { value: "waiting_for_customer", label: "Väntar på kund" },
  { value: "needs_help", label: "Behöver hjälp" },
  { value: "completed", label: "Klara" },
  { value: "failed", label: "Misslyckade" },
]

export const APPROVAL_STATUS_FILTERS = [
  { value: "pending" as const, label: "Väntande" },
  { value: "all" as const, label: "Alla" },
]
