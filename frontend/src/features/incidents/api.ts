import { deleteJson, get, patchJson, postJson } from "@/api/client"

import type {
  IncidentAssignSelfPayload,
  IncidentCreatePayload,
  IncidentDetail,
  IncidentFieldUpdatePayload,
  IncidentFilters,
  IncidentListResponse,
  IncidentNotePayload,
  IncidentSignalOut,
  IncidentStatusChangePayload,
  IncidentTenantOut,
  IncidentWriteResponse,
} from "./types"

function buildQuery(filters: IncidentFilters): string {
  const params = new URLSearchParams()
  if (filters.search?.trim()) params.set("search", filters.search.trim())
  if (filters.status) params.set("status", filters.status)
  if (filters.severity) params.set("severity", filters.severity)
  if (filters.tenantId) params.set("tenant_id", filters.tenantId)
  if (filters.owner) params.set("owner", filters.owner)
  if (filters.sort) params.set("sort", filters.sort)
  if (filters.order) params.set("order", filters.order)
  if (filters.limit != null) params.set("limit", String(filters.limit))
  if (filters.offset != null) params.set("offset", String(filters.offset))
  const query = params.toString()
  return query ? `?${query}` : ""
}

export function fetchIncidents(filters: IncidentFilters = {}): Promise<IncidentListResponse> {
  return get<IncidentListResponse>(`/admin/incidents${buildQuery(filters)}`)
}

export function fetchIncidentDetail(incidentId: string): Promise<IncidentDetail> {
  return get<IncidentDetail>(`/admin/incidents/${encodeURIComponent(incidentId)}`)
}

export function createIncident(body: IncidentCreatePayload): Promise<IncidentDetail> {
  return postJson<IncidentDetail>("/admin/incidents", body)
}

export function updateIncidentFields(
  incidentId: string,
  body: IncidentFieldUpdatePayload,
): Promise<IncidentWriteResponse> {
  return patchJson<IncidentWriteResponse>(
    `/admin/incidents/${encodeURIComponent(incidentId)}`,
    body,
  )
}

export function changeIncidentStatus(
  incidentId: string,
  body: IncidentStatusChangePayload,
): Promise<IncidentWriteResponse> {
  return postJson<IncidentWriteResponse>(
    `/admin/incidents/${encodeURIComponent(incidentId)}/status`,
    body,
  )
}

export function addIncidentNote(
  incidentId: string,
  body: IncidentNotePayload,
): Promise<IncidentWriteResponse> {
  return postJson<IncidentWriteResponse>(
    `/admin/incidents/${encodeURIComponent(incidentId)}/notes`,
    body,
  )
}

export function assignIncidentSelf(
  incidentId: string,
  body: IncidentAssignSelfPayload,
): Promise<IncidentWriteResponse> {
  return postJson<IncidentWriteResponse>(
    `/admin/incidents/${encodeURIComponent(incidentId)}/actions/assign-self`,
    body,
  )
}

export function linkIncidentTenant(
  incidentId: string,
  tenantId: string,
  body: { reason: string; confirmation: true },
): Promise<IncidentWriteResponse> {
  return postJson<IncidentWriteResponse>(
    `/admin/incidents/${encodeURIComponent(incidentId)}/tenants`,
    { tenant_id: tenantId, ...body },
  )
}

export function unlinkIncidentTenant(
  incidentId: string,
  tenantId: string,
  reason: string,
): Promise<IncidentWriteResponse> {
  const params = new URLSearchParams({
    reason,
    confirmation: "true",
  })
  return deleteJson<IncidentWriteResponse>(
    `/admin/incidents/${encodeURIComponent(incidentId)}/tenants/${encodeURIComponent(tenantId)}?${params}`,
  )
}

export function linkIncidentSignal(
  incidentId: string,
  tenantId: string,
  signalId: string,
  body: { reason: string; confirmation: true },
): Promise<IncidentWriteResponse> {
  return postJson<IncidentWriteResponse>(
    `/admin/incidents/${encodeURIComponent(incidentId)}/signals`,
    { tenant_id: tenantId, signal_id: signalId, ...body },
  )
}

export function unlinkIncidentSignal(
  incidentId: string,
  signalId: string,
  reason: string,
): Promise<IncidentWriteResponse> {
  const params = new URLSearchParams({
    reason,
    confirmation: "true",
  })
  return deleteJson<IncidentWriteResponse>(
    `/admin/incidents/${encodeURIComponent(incidentId)}/signals/${encodeURIComponent(signalId)}?${params}`,
  )
}

export type { IncidentDetail, IncidentListResponse, IncidentTenantOut, IncidentSignalOut }
