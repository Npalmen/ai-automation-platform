import { useQuery } from "@tanstack/react-query"

import { ApiError } from "@/api/client"

import { fetchCustomerSettings } from "../api"

export const CUSTOMER_SETTINGS_QUERY_KEY = ["admin", "customer-settings"] as const

export function useCustomerSettingsQuery(tenantId: string | undefined) {
  return useQuery({
    queryKey: [...CUSTOMER_SETTINGS_QUERY_KEY, tenantId],
    queryFn: () => fetchCustomerSettings(tenantId!),
    enabled: Boolean(tenantId),
    staleTime: 10_000,
    retry: (count, error) =>
      !(error instanceof ApiError && (error.status === 401 || error.status === 404)) && count < 1,
    refetchOnWindowFocus: false,
  })
}
