import { useMutation, useQueryClient } from "@tanstack/react-query"

import { ApiError } from "@/api/client"
import { NEEDS_HELP_QUERY_KEY } from "@/features/needsHelp/queries"
import { OVERVIEW_QUERY_KEY } from "@/features/overview/queries"
import { TENANTS_QUERY_KEY } from "@/features/customers/queries"

import {
  addIncidentNote,
  assignIncidentSelf,
  changeIncidentStatus,
  createIncident,
  linkIncidentSignal,
  linkIncidentTenant,
  unlinkIncidentSignal,
  unlinkIncidentTenant,
  updateIncidentFields,
} from "./api"
import { INCIDENTS_QUERY_KEY } from "./queries"
import type {
  IncidentAssignSelfPayload,
  IncidentCreatePayload,
  IncidentFieldUpdatePayload,
  IncidentNotePayload,
  IncidentStatusChangePayload,
} from "./types"

function invalidateAfterIncidentChange(
  queryClient: ReturnType<typeof useQueryClient>,
  incidentId?: string,
  options?: { signal?: boolean; tenant?: boolean },
) {
  queryClient.invalidateQueries({ queryKey: INCIDENTS_QUERY_KEY })
  if (incidentId) {
    queryClient.invalidateQueries({
      queryKey: [...INCIDENTS_QUERY_KEY, "detail", incidentId],
    })
  }
  queryClient.invalidateQueries({ queryKey: OVERVIEW_QUERY_KEY })
  if (options?.signal) {
    queryClient.invalidateQueries({ queryKey: NEEDS_HELP_QUERY_KEY })
  }
  if (options?.tenant) {
    queryClient.invalidateQueries({ queryKey: TENANTS_QUERY_KEY })
  }
}

export function formatIncidentError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return "Du saknar behörighet för denna åtgärd."
    if (error.status === 404) return "Incidenten eller resursen hittades inte."
    if (error.status === 409) {
      return typeof error.body === "object" && error.body && "detail" in error.body
        ? String((error.body as { detail: string }).detail)
        : "Åtgärden kunde inte utföras på grund av en konflikt."
    }
    if (error.status === 422) return "Ogiltig begäran. Kontrollera fälten."
  }
  return "Åtgärden misslyckades. Försök igen."
}

export function useCreateIncidentMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: IncidentCreatePayload) => createIncident(body),
    retry: false,
    onSuccess: () => {
      invalidateAfterIncidentChange(queryClient, undefined, {
        signal: true,
        tenant: true,
      })
    },
  })
}

export function useUpdateIncidentFieldsMutation(incidentId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: IncidentFieldUpdatePayload) =>
      updateIncidentFields(incidentId, body),
    retry: false,
    onSuccess: () => invalidateAfterIncidentChange(queryClient, incidentId),
  })
}

export function useChangeIncidentStatusMutation(incidentId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: IncidentStatusChangePayload) =>
      changeIncidentStatus(incidentId, body),
    retry: false,
    onSuccess: () => invalidateAfterIncidentChange(queryClient, incidentId),
  })
}

export function useAddIncidentNoteMutation(incidentId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: IncidentNotePayload) => addIncidentNote(incidentId, body),
    retry: false,
    onSuccess: () => invalidateAfterIncidentChange(queryClient, incidentId),
  })
}

export function useAssignSelfMutation(incidentId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: IncidentAssignSelfPayload) =>
      assignIncidentSelf(incidentId, body),
    retry: false,
    onSuccess: () => invalidateAfterIncidentChange(queryClient, incidentId),
  })
}

export function useLinkTenantMutation(incidentId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      tenantId,
      reason,
    }: {
      tenantId: string
      reason: string
    }) => linkIncidentTenant(incidentId, tenantId, { reason, confirmation: true }),
    retry: false,
    onSuccess: () =>
      invalidateAfterIncidentChange(queryClient, incidentId, { tenant: true }),
  })
}

export function useUnlinkTenantMutation(incidentId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      tenantId,
      reason,
    }: {
      tenantId: string
      reason: string
    }) => unlinkIncidentTenant(incidentId, tenantId, reason),
    retry: false,
    onSuccess: () =>
      invalidateAfterIncidentChange(queryClient, incidentId, { tenant: true }),
  })
}

export function useLinkSignalMutation(incidentId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      tenantId,
      signalId,
      reason,
    }: {
      tenantId: string
      signalId: string
      reason: string
    }) =>
      linkIncidentSignal(incidentId, tenantId, signalId, {
        reason,
        confirmation: true,
      }),
    retry: false,
    onSuccess: () =>
      invalidateAfterIncidentChange(queryClient, incidentId, { signal: true }),
  })
}

export function useUnlinkSignalMutation(incidentId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      signalId,
      reason,
    }: {
      signalId: string
      reason: string
    }) => unlinkIncidentSignal(incidentId, signalId, reason),
    retry: false,
    onSuccess: () =>
      invalidateAfterIncidentChange(queryClient, incidentId, { signal: true }),
  })
}
