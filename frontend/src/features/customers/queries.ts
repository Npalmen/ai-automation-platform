import { useQuery } from "@tanstack/react-query"

import { ApiError } from "@/api/client"

import { fetchTenantDetail, fetchTenants } from "./api"
import type { TenantListFilters } from "./types"

export const TENANTS_QUERY_KEY = ["admin", "tenants"] as const

export function useTenantsQuery(filters: TenantListFilters) {
  return useQuery({
    queryKey: [...TENANTS_QUERY_KEY, filters],
    queryFn: () => fetchTenants(filters),
    staleTime: 30_000,
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 401) && count < 1,
    refetchOnWindowFocus: false,
    placeholderData: (previous) => previous,
  })
}

export function useTenantDetailQuery(tenantId: string | undefined) {
  return useQuery({
    queryKey: [...TENANTS_QUERY_KEY, tenantId],
    queryFn: () => fetchTenantDetail(tenantId!),
    enabled: Boolean(tenantId),
    staleTime: 30_000,
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 401) && count < 1,
    refetchOnWindowFocus: false,
  })
}
