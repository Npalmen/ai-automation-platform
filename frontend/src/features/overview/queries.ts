import { useQuery } from "@tanstack/react-query"

import { ApiError } from "@/api/client"

import { fetchOverview } from "./api"

export const OVERVIEW_QUERY_KEY = ["operations", "overview"] as const

export function useOverviewQuery() {
  return useQuery({
    queryKey: OVERVIEW_QUERY_KEY,
    queryFn: fetchOverview,
    staleTime: 30_000,
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 401) && count < 1,
    refetchOnWindowFocus: false,
    placeholderData: (previous) => previous,
  })
}
