import { get } from "@/api/client"

import type { SystemStatusResponse } from "./types"

export function fetchSystemStatus(): Promise<SystemStatusResponse> {
  return get<SystemStatusResponse>("/admin/system/status")
}
