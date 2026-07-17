import { get } from "@/api/client"

import type {
  NeedsHelpFilters,
  NeedsHelpItemDetail,
  NeedsHelpQueueResponse,
} from "./types"

function buildQuery(filters: NeedsHelpFilters): string {
  const params = new URLSearchParams()
  if (filters.search?.trim()) {
    params.set("search", filters.search.trim())
  }
  if (filters.severity) {
    params.set("severity", filters.severity)
  }
  if (filters.category) {
    params.set("category", filters.category)
  }
  if (filters.tenantId) {
    params.set("tenant_id", filters.tenantId)
  }
  if (filters.sourceType) {
    params.set("source_type", filters.sourceType)
  }
  if (filters.safeRetry) {
    params.set("safe_retry", filters.safeRetry)
  }
  if (filters.externalImpact) {
    params.set("external_impact", filters.externalImpact)
  }
  if (filters.minimumAgeHours != null && filters.minimumAgeHours > 0) {
    params.set("minimum_age_hours", String(filters.minimumAgeHours))
  }
  if (filters.sort) {
    params.set("sort", filters.sort)
  }
  if (filters.order) {
    params.set("order", filters.order)
  }
  if (filters.limit != null) {
    params.set("limit", String(filters.limit))
  }
  if (filters.offset != null) {
    params.set("offset", String(filters.offset))
  }
  const query = params.toString()
  return query ? `?${query}` : ""
}

export function fetchNeedsHelpQueue(
  filters: NeedsHelpFilters = {},
): Promise<NeedsHelpQueueResponse> {
  return get<NeedsHelpQueueResponse>(`/admin/operations/needs-help${buildQuery(filters)}`)
}

export function fetchNeedsHelpItem(
  itemId: string,
  tenantId?: string,
): Promise<NeedsHelpItemDetail> {
  const params = new URLSearchParams()
  if (tenantId) {
    params.set("tenant_id", tenantId)
  }
  const query = params.toString()
  const suffix = query ? `?${query}` : ""
  return get<NeedsHelpItemDetail>(
    `/admin/operations/needs-help/${encodeURIComponent(itemId)}${suffix}`,
  )
}
