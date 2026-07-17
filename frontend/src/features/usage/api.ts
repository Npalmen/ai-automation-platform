import { get } from "@/api/client"

import type {
  UsageDays,
  UsageOverviewResponse,
  UsageTenantFilters,
  UsageTenantListResponse,
} from "./types"

export function buildOverviewQuery(days: UsageDays): string {
  return `?days=${days}`
}

export function buildTenantQuery(filters: UsageTenantFilters): string {
  const params = new URLSearchParams()
  if (filters.days != null) params.set("days", String(filters.days))
  if (filters.search?.trim()) params.set("search", filters.search.trim())
  if (filters.tenantStatus) params.set("tenant_status", filters.tenantStatus)
  if (filters.attentionStatus) params.set("attention_status", filters.attentionStatus)
  if (filters.minimumJobs != null) params.set("minimum_jobs", String(filters.minimumJobs))
  if (filters.hasOperatorBurden != null) {
    params.set("has_operator_burden", filters.hasOperatorBurden ? "true" : "false")
  }
  if (filters.sort) params.set("sort", filters.sort)
  if (filters.order) params.set("order", filters.order)
  if (filters.limit != null) params.set("limit", String(filters.limit))
  if (filters.offset != null) params.set("offset", String(filters.offset))
  const query = params.toString()
  return query ? `?${query}` : ""
}

export function fetchUsageOverview(days: UsageDays = 30): Promise<UsageOverviewResponse> {
  return get<UsageOverviewResponse>(`/admin/usage/overview${buildOverviewQuery(days)}`)
}

export function fetchUsageTenants(
  filters: UsageTenantFilters = {},
): Promise<UsageTenantListResponse> {
  return get<UsageTenantListResponse>(`/admin/usage/tenants${buildTenantQuery(filters)}`)
}
