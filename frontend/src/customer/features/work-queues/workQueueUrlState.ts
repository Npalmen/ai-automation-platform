import type { CustomerStatus } from "@/customer/types/overview"
import {
  WORK_QUEUE_PAGE_SIZE,
  WORK_QUEUE_SORT_OPTIONS,
  type WorkQueueSortKey,
} from "@/customer/features/work-queues/workQueueConstants"

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

const VALID_SORT_KEYS = new Set<WorkQueueSortKey>([
  "priority_rank",
  "updated_at",
  "created_at",
])

export type WorkQueueUrlState = {
  status: CustomerStatus | "all"
  sort: WorkQueueSortKey
  order: "asc" | "desc"
  page: number
}

export type ApprovalUrlState = {
  status: "pending" | "all"
  page: number
}

function parsePositiveInt(value: string | null, fallback: number): number {
  if (!value) return fallback
  const parsed = Number.parseInt(value, 10)
  if (!Number.isFinite(parsed) || parsed < 1) return fallback
  return parsed
}

export function parseWorkQueueUrlState(
  searchParams: URLSearchParams,
): WorkQueueUrlState {
  const rawStatus = searchParams.get("status") ?? "all"
  const status = VALID_STATUSES.has(rawStatus as CustomerStatus | "all")
    ? (rawStatus as CustomerStatus | "all")
    : "all"

  const rawSort = searchParams.get("sort") ?? "priority_rank"
  const sort = VALID_SORT_KEYS.has(rawSort as WorkQueueSortKey)
    ? (rawSort as WorkQueueSortKey)
    : "priority_rank"

  const rawOrder = searchParams.get("order")
  const order = rawOrder === "asc" || rawOrder === "desc" ? rawOrder : "asc"

  const matchedSort = WORK_QUEUE_SORT_OPTIONS.find(
    (option) => option.sort === sort && option.order === order,
  )
  const resolvedSort = matchedSort?.sort ?? sort
  const resolvedOrder = matchedSort?.order ?? (sort === "priority_rank" ? "asc" : "desc")

  return {
    status,
    sort: resolvedSort,
    order: resolvedOrder,
    page: parsePositiveInt(searchParams.get("page"), 1),
  }
}

export function buildWorkQueueSearchParams(
  state: WorkQueueUrlState,
): URLSearchParams {
  const params = new URLSearchParams()
  if (state.status !== "all") params.set("status", state.status)
  if (state.sort !== "priority_rank" || state.order !== "asc") {
    params.set("sort", state.sort)
    params.set("order", state.order)
  }
  if (state.page > 1) params.set("page", String(state.page))
  return params
}

export function workQueueOffset(page: number): number {
  return (page - 1) * WORK_QUEUE_PAGE_SIZE
}

export function parseApprovalUrlState(
  searchParams: URLSearchParams,
): ApprovalUrlState {
  const rawStatus = searchParams.get("status") ?? "pending"
  return {
    status: rawStatus === "all" ? "all" : "pending",
    page: parsePositiveInt(searchParams.get("page"), 1),
  }
}

export function buildApprovalSearchParams(
  state: ApprovalUrlState,
): URLSearchParams {
  const params = new URLSearchParams()
  if (state.status !== "pending") params.set("status", state.status)
  if (state.page > 1) params.set("page", String(state.page))
  return params
}

export function normalizePageForTotal(page: number, total: number, limit: number): number {
  if (total === 0) return 1
  const maxPage = Math.max(1, Math.ceil(total / limit))
  return Math.min(page, maxPage)
}
