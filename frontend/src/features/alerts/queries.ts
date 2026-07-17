import { useQuery } from "@tanstack/react-query"

import { ApiError } from "@/api/client"

import { fetchAlertDetail, fetchAlertSummary, fetchAlerts, fetchOperatorDigests } from "./api"
import type { AlertFilters } from "./types"

export const ALERTS_QUERY_KEY = ["admin", "alerts"] as const

export function useAlertSummaryQuery() {
  return useQuery({
    queryKey: [...ALERTS_QUERY_KEY, "summary"],
    queryFn: fetchAlertSummary,
    staleTime: 30_000,
    refetchInterval: 60_000,
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 401) && count < 1,
    refetchOnWindowFocus: true,
  })
}

export function useAlertsQuery(filters: AlertFilters) {
  return useQuery({
    queryKey: [...ALERTS_QUERY_KEY, "list", filters],
    queryFn: () => fetchAlerts(filters),
    staleTime: 30_000,
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 401) && count < 1,
    refetchOnWindowFocus: false,
    placeholderData: (previous) => previous,
  })
}

export function useAlertDetailQuery(alertId: string | undefined) {
  return useQuery({
    queryKey: [...ALERTS_QUERY_KEY, "detail", alertId],
    queryFn: () => fetchAlertDetail(alertId!),
    enabled: Boolean(alertId),
    staleTime: 15_000,
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 401) && count < 1,
    refetchOnWindowFocus: false,
  })
}

export function useOperatorDigestsQuery() {
  return useQuery({
    queryKey: [...ALERTS_QUERY_KEY, "digests"],
    queryFn: fetchOperatorDigests,
    staleTime: 60_000,
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 401) && count < 1,
    refetchOnWindowFocus: false,
  })
}
