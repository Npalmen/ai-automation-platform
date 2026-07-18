import { useMutation, useQueryClient } from "@tanstack/react-query"

import { ApiError } from "@/api/client"
import { NEEDS_HELP_QUERY_KEY } from "@/features/needsHelp/queries"
import { OVERVIEW_QUERY_KEY } from "@/features/overview/queries"
import { TENANTS_QUERY_KEY } from "@/features/customers/queries"

import {
  pauseTenantAutomation,
  pauseTenantScheduler,
  rejectTenantApproval,
  approveTenantApproval,
  resumeTenantAutomation,
  resumeTenantScheduler,
} from "./api"
import type { OperatorActionRequest, OperatorActionResponse } from "./types"

type ActionBody = Omit<OperatorActionRequest, "idempotency_key">

function invalidateAfterAction(
  queryClient: ReturnType<typeof useQueryClient>,
  tenantId: string,
) {
  void queryClient.invalidateQueries({ queryKey: [...TENANTS_QUERY_KEY, tenantId] })
  void queryClient.invalidateQueries({ queryKey: TENANTS_QUERY_KEY })
  void queryClient.invalidateQueries({ queryKey: NEEDS_HELP_QUERY_KEY })
  void queryClient.invalidateQueries({ queryKey: OVERVIEW_QUERY_KEY })
}

function useOperatorMutation(
  mutationFn: (args: { tenantId: string; body: ActionBody }) => Promise<OperatorActionResponse>,
  tenantId: string,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ActionBody) => mutationFn({ tenantId, body }),
    retry: false,
    onSuccess: () => {
      invalidateAfterAction(queryClient, tenantId)
    },
  })
}

export function usePauseAutomationMutation(tenantId: string) {
  return useOperatorMutation(
    ({ tenantId: id, body }) => pauseTenantAutomation(id, body),
    tenantId,
  )
}

export function useResumeAutomationMutation(tenantId: string) {
  return useOperatorMutation(
    ({ tenantId: id, body }) => resumeTenantAutomation(id, body),
    tenantId,
  )
}

export function usePauseSchedulerMutation(tenantId: string) {
  return useOperatorMutation(
    ({ tenantId: id, body }) => pauseTenantScheduler(id, body),
    tenantId,
  )
}

export function useResumeSchedulerMutation(tenantId: string) {
  return useOperatorMutation(
    ({ tenantId: id, body }) => resumeTenantScheduler(id, body),
    tenantId,
  )
}

export function useRejectApprovalMutation(tenantId: string, approvalId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ActionBody) => rejectTenantApproval(tenantId, approvalId, body),
    retry: false,
    onSuccess: () => {
      invalidateAfterAction(queryClient, tenantId)
    },
  })
}

export function useApproveApprovalMutation(tenantId: string, approvalId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ActionBody) => approveTenantApproval(tenantId, approvalId, body),
    retry: false,
    onSuccess: () => {
      invalidateAfterAction(queryClient, tenantId)
    },
  })
}

export function formatOperatorActionError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return "Du saknar behörighet för denna åtgärd."
    }
    if (error.status === 404) {
      return "Resursen hittades inte."
    }
    if (error.status === 409) {
      const detail =
        typeof error.body === "object" &&
        error.body !== null &&
        "detail" in error.body &&
        typeof (error.body as { detail: unknown }).detail === "string"
          ? (error.body as { detail: string }).detail
          : "Åtgärden är inte giltig i aktuellt tillstånd."
      return detail
    }
    if (error.status === 422) {
      return "Ogiltig begäran. Kontrollera anledning och bekräftelse."
    }
    if (error.status === 500) {
      return "Resultatet kunde inte verifieras. Kontrollera status innan du försöker igen."
    }
    return "Åtgärden misslyckades."
  }
  if (error instanceof Error && error.message) {
    return "Resultatet kunde inte verifieras."
  }
  return "Ett oväntat fel inträffade."
}
