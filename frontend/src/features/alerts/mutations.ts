import { useMutation, useQueryClient } from "@tanstack/react-query"

import { ApiError } from "@/api/client"
import { OVERVIEW_QUERY_KEY } from "@/features/overview/queries"

import { acknowledgeAlert, resolveAlert } from "./api"
import { ALERTS_QUERY_KEY } from "./queries"
import type { AlertAcknowledgePayload, AlertResolvePayload } from "./types"

function invalidateAfterAlertChange(
  queryClient: ReturnType<typeof useQueryClient>,
  alertId?: string,
) {
  queryClient.invalidateQueries({ queryKey: ALERTS_QUERY_KEY })
  if (alertId) {
    queryClient.invalidateQueries({
      queryKey: [...ALERTS_QUERY_KEY, "detail", alertId],
    })
  }
  queryClient.invalidateQueries({ queryKey: OVERVIEW_QUERY_KEY })
}

export function formatAlertError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return "Du saknar behörighet för denna åtgärd."
    if (error.status === 404) return "Larmet hittades inte."
    if (error.status === 409) {
      return typeof error.body === "object" && error.body && "detail" in error.body
        ? String((error.body as { detail: string }).detail)
        : "Åtgärden kunde inte utföras på grund av en konflikt."
    }
    if (error.status === 422) return "Ogiltig begäran. Kontrollera fälten."
  }
  return "Åtgärden misslyckades. Försök igen."
}

export function useAcknowledgeAlertMutation(alertId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: AlertAcknowledgePayload) => acknowledgeAlert(alertId, body),
    onSuccess: () => invalidateAfterAlertChange(queryClient, alertId),
  })
}

export function useResolveAlertMutation(alertId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: AlertResolvePayload) => resolveAlert(alertId, body),
    onSuccess: () => invalidateAfterAlertChange(queryClient, alertId),
  })
}
