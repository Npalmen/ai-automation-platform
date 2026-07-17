import { get, postJson } from "@/api/client"

import type {
  AlertAcknowledgePayload,
  AlertDetail,
  AlertFilters,
  AlertListResponse,
  AlertResolvePayload,
  AlertSummaryResponse,
  AlertWriteResponse,
  OperatorDigestListResponse,
  OperatorDigestResponse,
} from "./types"

function buildQuery(filters: AlertFilters): string {
  const params = new URLSearchParams()
  if (filters.status) params.set("status", filters.status)
  if (filters.severity) params.set("severity", filters.severity)
  if (filters.tenantId) params.set("tenant_id", filters.tenantId)
  if (filters.alertType) params.set("alert_type", filters.alertType)
  if (filters.limit != null) params.set("limit", String(filters.limit))
  if (filters.offset != null) params.set("offset", String(filters.offset))
  const query = params.toString()
  return query ? `?${query}` : ""
}

export function fetchAlertSummary(): Promise<AlertSummaryResponse> {
  return get<AlertSummaryResponse>("/admin/alerts/summary")
}

export function fetchAlerts(filters: AlertFilters = {}): Promise<AlertListResponse> {
  return get<AlertListResponse>(`/admin/alerts${buildQuery(filters)}`)
}

export function fetchAlertDetail(alertId: string): Promise<AlertDetail> {
  return get<AlertDetail>(`/admin/alerts/${encodeURIComponent(alertId)}`)
}

export function acknowledgeAlert(
  alertId: string,
  body: AlertAcknowledgePayload,
): Promise<AlertWriteResponse> {
  return postJson<AlertWriteResponse>(
    `/admin/alerts/${encodeURIComponent(alertId)}/acknowledge`,
    body,
  )
}

export function resolveAlert(
  alertId: string,
  body: AlertResolvePayload,
): Promise<AlertWriteResponse> {
  return postJson<AlertWriteResponse>(
    `/admin/alerts/${encodeURIComponent(alertId)}/resolve`,
    body,
  )
}

export function fetchOperatorDigests(): Promise<OperatorDigestListResponse> {
  return get<OperatorDigestListResponse>("/admin/operator-digests")
}

export function fetchOperatorDigest(digestId: string): Promise<OperatorDigestResponse> {
  return get<OperatorDigestResponse>(
    `/admin/operator-digests/${encodeURIComponent(digestId)}`,
  )
}
