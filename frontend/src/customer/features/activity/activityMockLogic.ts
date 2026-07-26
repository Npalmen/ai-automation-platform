import type { ActivityListItem } from "@/customer/types/activity"
import type { ActivityListParams } from "@/customer/types/activity"
import type { ListResponse } from "@/customer/types/lists"

function compareValues(
  left: string,
  right: string,
  order: "asc" | "desc",
): number {
  if (left === right) return 0
  const result = left < right ? -1 : 1
  return order === "asc" ? result : -result
}

export function filterActivityItems(
  items: ActivityListItem[],
  params: ActivityListParams,
): ActivityListItem[] {
  if (params.type === "all") return items
  return items.filter((item) => item.type === params.type)
}

export function buildActivityListResponse(
  allItems: ActivityListItem[],
  params: ActivityListParams,
  partialErrors: ListResponse<ActivityListItem>["partial_errors"] = [],
): ListResponse<ActivityListItem> {
  const filtered = filterActivityItems(allItems, params)
  const sorted = [...filtered].sort((left, right) =>
    compareValues(left.at, right.at, "desc"),
  )
  const safeLimit = Math.max(1, params.limit)
  const safeOffset = Math.max(0, params.offset)

  return {
    items: sorted.slice(safeOffset, safeOffset + safeLimit),
    total: sorted.length,
    limit: safeLimit,
    offset: safeOffset,
    partial_errors: partialErrors,
  }
}
