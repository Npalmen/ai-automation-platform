import { postJson } from "@/api/client"

import type { OperatorActionRequest, OperatorActionResponse } from "./types"

function newIdempotencyKey(): string {
  return crypto.randomUUID()
}

function withIdempotency(body: Omit<OperatorActionRequest, "idempotency_key">): OperatorActionRequest {
  return {
    ...body,
    idempotency_key: newIdempotencyKey(),
  }
}

export function pauseTenantAutomation(
  tenantId: string,
  body: Omit<OperatorActionRequest, "idempotency_key">,
): Promise<OperatorActionResponse> {
  return postJson<OperatorActionResponse>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/actions/pause`,
    withIdempotency(body),
  )
}

export function resumeTenantAutomation(
  tenantId: string,
  body: Omit<OperatorActionRequest, "idempotency_key">,
): Promise<OperatorActionResponse> {
  return postJson<OperatorActionResponse>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/actions/resume`,
    withIdempotency(body),
  )
}

export function pauseTenantScheduler(
  tenantId: string,
  body: Omit<OperatorActionRequest, "idempotency_key">,
): Promise<OperatorActionResponse> {
  return postJson<OperatorActionResponse>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/scheduler/pause`,
    withIdempotency(body),
  )
}

export function resumeTenantScheduler(
  tenantId: string,
  body: Omit<OperatorActionRequest, "idempotency_key">,
): Promise<OperatorActionResponse> {
  return postJson<OperatorActionResponse>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/scheduler/resume`,
    withIdempotency(body),
  )
}

export function rejectTenantApproval(
  tenantId: string,
  approvalId: string,
  body: Omit<OperatorActionRequest, "idempotency_key">,
): Promise<OperatorActionResponse> {
  return postJson<OperatorActionResponse>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/approvals/${encodeURIComponent(approvalId)}/reject`,
    withIdempotency(body),
  )
}
