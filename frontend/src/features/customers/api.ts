import { get } from "@/api/client"

import type { TenantDetailResponse, TenantListFilters, TenantListResponse } from "./types"

function buildQuery(filters: TenantListFilters): string {
  const params = new URLSearchParams()
  if (filters.search?.trim()) {
    params.set("search", filters.search.trim())
  }
  if (filters.status) {
    params.set("status", filters.status)
  }
  if (filters.health) {
    params.set("health", filters.health)
  }
  if (filters.sort) {
    params.set("sort", filters.sort)
  }
  if (filters.order) {
    params.set("order", filters.order)
  }
  const query = params.toString()
  return query ? `?${query}` : ""
}

export function fetchTenants(filters: TenantListFilters = {}): Promise<TenantListResponse> {
  return get<TenantListResponse>(`/admin/tenants${buildQuery(filters)}`)
}

export function fetchTenantDetail(tenantId: string): Promise<TenantDetailResponse> {
  return get<TenantDetailResponse>(`/admin/tenants/${encodeURIComponent(tenantId)}/overview`)
}
