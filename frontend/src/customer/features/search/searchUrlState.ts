import type { CustomerStatus } from "@/customer/types/overview"
import {
  WORK_QUEUE_PAGE_SIZE,
  WORK_QUEUE_SORT_OPTIONS,
  type WorkQueueSortKey,
} from "@/customer/features/work-queues/workQueueConstants"
import { isDateRangeInvalid } from "@/customer/features/work-queues/dateFilterUtils"

const VALID_STATUSES = new Set<CustomerStatus | "all">([
  "all",
  "new",
  "prioritized",
  "in_progress",
  "waiting_for_decision",
  "waiting_for_customer",
  "prepared",
  "scheduled",
  "completed",
  "needs_help",
  "failed",
  "cancelled",
  "unknown",
])

const VALID_TYPES = new Set(["all", "lead", "support", "needs_help"])
const VALID_SORT_KEYS = new Set<WorkQueueSortKey>([
  "priority_rank",
  "updated_at",
  "created_at",
])

export type SearchUrlState = {
  q: string
  type: "all" | "lead" | "support" | "needs_help"
  status: CustomerStatus | "all"
  from: string
  to: string
  sort: WorkQueueSortKey
  order: "asc" | "desc"
  page: number
}

function parsePositiveInt(value: string | null, fallback: number): number {
  if (!value) return fallback
  const parsed = Number.parseInt(value, 10)
  if (!Number.isFinite(parsed) || parsed < 1) return fallback
  return parsed
}

export function parseSearchUrlState(searchParams: URLSearchParams): SearchUrlState {
  const rawType = searchParams.get("type") ?? "all"
  const rawStatus = searchParams.get("status") ?? "all"
  const rawSort = searchParams.get("sort") ?? "priority_rank"
  const rawOrder = searchParams.get("order")
  const order = rawOrder === "asc" || rawOrder === "desc" ? rawOrder : "asc"
  const sort = VALID_SORT_KEYS.has(rawSort as WorkQueueSortKey)
    ? (rawSort as WorkQueueSortKey)
    : "priority_rank"

  return {
    q: searchParams.get("q")?.trim() ?? "",
    type: VALID_TYPES.has(rawType) ? (rawType as SearchUrlState["type"]) : "all",
    status: VALID_STATUSES.has(rawStatus as CustomerStatus | "all")
      ? (rawStatus as CustomerStatus | "all")
      : "all",
    from: searchParams.get("from")?.trim() ?? "",
    to: searchParams.get("to")?.trim() ?? "",
    sort,
    order,
    page: parsePositiveInt(searchParams.get("page"), 1),
  }
}

export function buildSearchUrlParams(state: SearchUrlState): URLSearchParams {
  const params = new URLSearchParams()
  if (state.q) params.set("q", state.q)
  if (state.type !== "all") params.set("type", state.type)
  if (state.status !== "all") params.set("status", state.status)
  if (state.from) params.set("from", state.from)
  if (state.to) params.set("to", state.to)
  if (state.sort !== "priority_rank" || state.order !== "asc") {
    params.set("sort", state.sort)
    params.set("order", state.order)
  }
  if (state.page > 1) params.set("page", String(state.page))
  return params
}

export function hasInvalidSearchDateRange(state: SearchUrlState): boolean {
  if (!state.from || !state.to) return false
  return isDateRangeInvalid(state.from, state.to)
}

export { WORK_QUEUE_PAGE_SIZE, WORK_QUEUE_SORT_OPTIONS }

export function searchOffset(page: number): number {
  return (page - 1) * WORK_QUEUE_PAGE_SIZE
}

export function normalizePageForTotal(page: number, total: number, limit: number): number {
  if (total === 0) return 1
  const maxPage = Math.max(1, Math.ceil(total / limit))
  return Math.min(page, maxPage)
}
