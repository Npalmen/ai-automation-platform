import { useQuery } from "@tanstack/react-query"

import { ApiError } from "@/api/client"

import { fetchUsageOverview, fetchUsageTenants } from "./api"
import type { UsageDays, UsageTenantFilters } from "./types"

export const USAGE_QUERY_KEY = ["admin", "usage"] as const

export function useUsageOverviewQuery(days: UsageDays = 30) {
  return useQuery({
    queryKey: [...USAGE_QUERY_KEY, "overview", days],
    queryFn: () => fetchUsageOverview(days),
    staleTime: 30_000,
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 401) && count < 1,
    refetchOnWindowFocus: false,
  })
}

export function useUsageTenantsQuery(filters: UsageTenantFilters) {
  return useQuery({
    queryKey: [...USAGE_QUERY_KEY, "tenants", filters],
    queryFn: () => fetchUsageTenants(filters),
    staleTime: 30_000,
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 401) && count < 1,
    refetchOnWindowFocus: false,
    placeholderData: (previous) => previous,
  })
}
