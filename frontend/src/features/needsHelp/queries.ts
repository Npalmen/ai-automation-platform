import { useQuery } from "@tanstack/react-query"

import { ApiError } from "@/api/client"

import { fetchNeedsHelpItem, fetchNeedsHelpQueue } from "./api"
import type { NeedsHelpFilters } from "./types"

export const NEEDS_HELP_QUERY_KEY = ["admin", "needs-help"] as const

export function useNeedsHelpQueueQuery(filters: NeedsHelpFilters) {
  return useQuery({
    queryKey: [...NEEDS_HELP_QUERY_KEY, "queue", filters],
    queryFn: () => fetchNeedsHelpQueue(filters),
    staleTime: 30_000,
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 401) && count < 1,
    refetchOnWindowFocus: false,
    placeholderData: (previous) => previous,
  })
}

export function useNeedsHelpItemQuery(itemId: string | undefined, tenantId?: string) {
  return useQuery({
    queryKey: [...NEEDS_HELP_QUERY_KEY, "item", itemId, tenantId],
    queryFn: () => fetchNeedsHelpItem(itemId!, tenantId),
    enabled: Boolean(itemId),
    staleTime: 30_000,
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 401) && count < 1,
    refetchOnWindowFocus: false,
  })
}
