import type { ApprovalListParams } from "@/customer/types/approvals"
import type { ApprovalListItem } from "@/customer/types/approvals"
import type { ListResponse } from "@/customer/types/lists"
import { matchesCreatedDateRange } from "@/customer/features/work-queues/dateFilterUtils"
import type {
  WorkItemListItem,
  WorkItemListParams,
} from "@/customer/types/work-items"

function compareValues(
  left: string | number,
  right: string | number,
  order: "asc" | "desc",
): number {
  if (left === right) return 0
  const result = left < right ? -1 : 1
  return order === "asc" ? result : -result
}

function normalizeSearchText(value: string): string {
  return value.trim().toLocaleLowerCase("sv-SE")
}

export function matchesWorkItemSearch(
  item: WorkItemListItem,
  query: string | undefined,
): boolean {
  const needle = normalizeSearchText(query ?? "")
  if (!needle) return true

  const haystack = [
    item.title,
    item.customer_name,
    item.customer_email,
    item.summary,
  ]
    .filter((value): value is string => Boolean(value))
    .join(" ")
    .toLocaleLowerCase("sv-SE")

  return haystack.includes(needle)
}

export function filterWorkItems(
  items: WorkItemListItem[],
  params: WorkItemListParams,
): WorkItemListItem[] {
  let filtered = items

  if (params.type !== "all") {
    filtered = filtered.filter((item) => item.type === params.type)
  }

  if (params.status) {
    filtered = filtered.filter(
      (item) => item.customer_status === params.status,
    )
  }

  if (params.q) {
    filtered = filtered.filter((item) => matchesWorkItemSearch(item, params.q))
  }

  if (params.from || params.to) {
    filtered = filtered.filter((item) =>
      matchesCreatedDateRange(item.created_at, params.from, params.to),
    )
  }

  return filtered
}

export function sortWorkItems(
  items: WorkItemListItem[],
  params: WorkItemListParams,
): WorkItemListItem[] {
  const sortKey = params.sort ?? "priority_rank"
  const order = params.order ?? "asc"
  const sorted = [...items]

  sorted.sort((left, right) => {
    if (sortKey === "priority_rank") {
      return compareValues(left.priority_rank, right.priority_rank, order)
    }
    if (sortKey === "created_at") {
      return compareValues(left.created_at, right.created_at, order)
    }
    return compareValues(left.updated_at, right.updated_at, order)
  })

  return sorted
}

export function paginateList<T>(
  items: T[],
  limit: number,
  offset: number,
): { items: T[]; total: number } {
  const safeLimit = Math.max(1, limit)
  const safeOffset = Math.max(0, offset)
  return {
    items: items.slice(safeOffset, safeOffset + safeLimit),
    total: items.length,
  }
}

export function buildWorkItemListResponse(
  allItems: WorkItemListItem[],
  params: WorkItemListParams,
  partialErrors: ListResponse<WorkItemListItem>["partial_errors"] = [],
): ListResponse<WorkItemListItem> {
  const filtered = filterWorkItems(allItems, params)
  const sorted = sortWorkItems(filtered, params)
  const page = paginateList(sorted, params.limit, params.offset)

  return {
    items: page.items,
    total: page.total,
    limit: params.limit,
    offset: params.offset,
    partial_errors: partialErrors,
  }
}

export function filterApprovals(
  items: ApprovalListItem[],
  params: ApprovalListParams,
): ApprovalListItem[] {
  if (params.status === "all") return items
  return items.filter(
    (item) => item.customer_status === "waiting_for_decision"
      || item.customer_status === "prepared",
  )
}

export function buildApprovalListResponse(
  allItems: ApprovalListItem[],
  params: ApprovalListParams,
  partialErrors: ListResponse<ApprovalListItem>["partial_errors"] = [],
): ListResponse<ApprovalListItem> {
  const filtered = filterApprovals(allItems, params)
  const sorted = [...filtered].sort((left, right) =>
    compareValues(left.requested_at, right.requested_at, "desc"),
  )
  const page = paginateList(sorted, params.limit, params.offset)

  return {
    items: page.items,
    total: page.total,
    limit: params.limit,
    offset: params.offset,
    partial_errors: partialErrors,
  }
}
