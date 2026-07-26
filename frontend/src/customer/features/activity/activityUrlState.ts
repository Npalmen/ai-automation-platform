import type { ActivityListParams } from "@/customer/types/activity"
import { WORK_QUEUE_PAGE_SIZE } from "@/customer/features/work-queues/workQueueConstants"

export type ActivityUrlState = {
  type: ActivityListParams["type"]
  page: number
}

const VALID_TYPES = new Set<ActivityListParams["type"]>([
  "all",
  "lead",
  "support",
  "invoice",
])

function parsePositiveInt(value: string | null, fallback: number): number {
  if (!value) return fallback
  const parsed = Number.parseInt(value, 10)
  if (!Number.isFinite(parsed) || parsed < 1) return fallback
  return parsed
}

export function parseActivityUrlState(searchParams: URLSearchParams): ActivityUrlState {
  const rawType = searchParams.get("type") ?? "all"
  return {
    type: VALID_TYPES.has(rawType as ActivityListParams["type"])
      ? (rawType as ActivityListParams["type"])
      : "all",
    page: parsePositiveInt(searchParams.get("page"), 1),
  }
}

export function buildActivitySearchParams(state: ActivityUrlState): URLSearchParams {
  const params = new URLSearchParams()
  if (state.type !== "all") params.set("type", state.type)
  if (state.page > 1) params.set("page", String(state.page))
  return params
}

export function activityOffset(page: number): number {
  return (page - 1) * WORK_QUEUE_PAGE_SIZE
}

export function normalizePageForTotal(page: number, total: number, limit: number): number {
  if (total === 0) return 1
  const maxPage = Math.max(1, Math.ceil(total / limit))
  return Math.min(page, maxPage)
}

export const ACTIVITY_TYPE_FILTERS = [
  { value: "all" as const, label: "Alla" },
  { value: "lead" as const, label: "Leads" },
  { value: "support" as const, label: "Kundfrågor" },
  { value: "invoice" as const, label: "Fakturor" },
]
