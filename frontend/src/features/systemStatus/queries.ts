import { useQuery } from "@tanstack/react-query"

import { fetchSystemStatus } from "./api"

export const SYSTEM_STATUS_QUERY_KEY = ["admin", "system", "status"] as const

export function useSystemStatusQuery() {
  return useQuery({
    queryKey: SYSTEM_STATUS_QUERY_KEY,
    queryFn: fetchSystemStatus,
    staleTime: 60_000,
  })
}
