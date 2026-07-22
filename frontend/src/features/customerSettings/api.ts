import { get, patchJson, postJson } from "@/api/client"

import type {
  CustomerSettingsAggregate,
  CustomerSettingsPatchRequest,
  CustomerSettingsPatchResponse,
  CustomerSettingsPreviewResponse,
} from "./types"

export function fetchCustomerSettings(tenantId: string): Promise<CustomerSettingsAggregate> {
  return get<CustomerSettingsAggregate>(`/admin/tenants/${encodeURIComponent(tenantId)}/settings`)
}

export function patchCustomerSettingsDomain(
  tenantId: string,
  domain: string,
  body: CustomerSettingsPatchRequest,
): Promise<CustomerSettingsPatchResponse> {
  return patchJson<CustomerSettingsPatchResponse>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/settings/${encodeURIComponent(domain)}`,
    body,
  )
}

export function previewCustomerSettingsDomain(
  tenantId: string,
  domain: string,
  payload: Record<string, unknown>,
): Promise<CustomerSettingsPreviewResponse> {
  return postJson<CustomerSettingsPreviewResponse>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/settings/${encodeURIComponent(domain)}/preview`,
    { payload },
  )
}
