import { get, postJson, deleteJson } from "@/api/client"

export type LifecycleInfo = {
  tenant_id: string
  lifecycle_status: string
  lifecycle_label_sv: string
  config_version: number
  is_test_tenant: boolean
  operations_paused: boolean
  scheduler_run_mode: string | null
  lifecycle_updated_at: string | null
  lifecycle_updated_by: string | null
  last_config_updated_by: string | null
}

export type ActivationSnapshot = {
  id: string
  tenant_id: string
  config_version: number
  plan_hash: string
  readiness_check_version: number
  activated_by_operator_id: string
  activated_at: string
}

export type IntegrationInvitation = {
  id: string
  integration_key: string
  contact_email: string
  contact_name: string | null
  status: string
  expires_at: string
  connected_account_email: string | null
}

export function fetchLifecycle(tenantId: string): Promise<LifecycleInfo> {
  return get<LifecycleInfo>(`/admin/tenants/${encodeURIComponent(tenantId)}/lifecycle`)
}

export function archiveTenant(
  tenantId: string,
  configVersion: number,
  reason?: string,
): Promise<LifecycleInfo> {
  return postJson<LifecycleInfo>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/lifecycle/archive`,
    { config_version: configVersion, reason },
  )
}

export function restoreTenant(
  tenantId: string,
  configVersion: number,
  reason?: string,
): Promise<LifecycleInfo> {
  return postJson<LifecycleInfo>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/lifecycle/restore`,
    { config_version: configVersion, reason },
  )
}

export function fetchActivationHistory(tenantId: string): Promise<{ items: ActivationSnapshot[] }> {
  return get(`/admin/tenants/${encodeURIComponent(tenantId)}/activation-history`)
}

export function fetchInvitations(tenantId: string): Promise<IntegrationInvitation[]> {
  return get(`/admin/tenants/${encodeURIComponent(tenantId)}/integrations/invitations`)
}

export function createInvitation(
  tenantId: string,
  body: { integration_key: string; contact_email: string; contact_name?: string },
): Promise<{ invitation_id: string; invite_path: string }> {
  return postJson(`/admin/tenants/${encodeURIComponent(tenantId)}/integrations/invitations`, body)
}

export function revokeInvitation(tenantId: string, invitationId: string): Promise<{ status: string }> {
  return postJson(
    `/admin/tenants/${encodeURIComponent(tenantId)}/integrations/invitations/${encodeURIComponent(invitationId)}/revoke`,
    {},
  )
}

export function deleteTestTenant(
  tenantId: string,
  body: { confirm_tenant_id: string; reason: string },
): Promise<{ status: string }> {
  return deleteJson(`/admin/tenants/${encodeURIComponent(tenantId)}`, {
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}
