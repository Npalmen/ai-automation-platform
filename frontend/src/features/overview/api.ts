import { get } from "@/api/client"

import type { OperationsOverviewResponse } from "./types"

export function fetchOverview(): Promise<OperationsOverviewResponse> {
  return get<OperationsOverviewResponse>("/admin/operations/overview")
}
