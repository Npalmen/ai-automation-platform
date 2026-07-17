import { useQuery } from "@tanstack/react-query"

import { ApiError } from "@/api/client"

import { fetchIncidentDetail, fetchIncidents } from "./api"
import type { IncidentFilters } from "./types"

export const INCIDENTS_QUERY_KEY = ["admin", "incidents"] as const

export function useIncidentsQuery(filters: IncidentFilters) {
  return useQuery({
    queryKey: [...INCIDENTS_QUERY_KEY, "list", filters],
    queryFn: () => fetchIncidents(filters),
    staleTime: 30_000,
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 401) && count < 1,
    refetchOnWindowFocus: false,
    placeholderData: (previous) => previous,
  })
}

export function useIncidentDetailQuery(incidentId: string | undefined) {
  return useQuery({
    queryKey: [...INCIDENTS_QUERY_KEY, "detail", incidentId],
    queryFn: () => fetchIncidentDetail(incidentId!),
    enabled: Boolean(incidentId),
    staleTime: 15_000,
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 401) && count < 1,
    refetchOnWindowFocus: false,
  })
}
