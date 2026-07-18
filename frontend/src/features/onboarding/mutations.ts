import { useMutation, useQueryClient } from "@tanstack/react-query"

import { ApiError } from "@/api/client"
import { TENANTS_QUERY_KEY } from "@/features/customers/queries"

import {
  activateOnboardingSession,
  cancelOnboardingSession,
  createOnboardingSession,
  patchDataStartStep,
  patchOnboardingAutomation,
  patchOnboardingIdentity,
  patchOnboardingModules,
  patchRoutingStep,
  patchServiceProfileStep,
  previewRoutingStep,
  resetRoutingStep,
  runOnboardingReadiness,
  patchIntegrationsStep,
  connectIntegrationStep,
  verifyIntegrationStep,
  patchExternalRoutingStep,
  previewExternalRoutingStep,
  resetExternalRoutingStep,
  unrequestIntegrationStep,
  localUnlinkIntegrationStep,
} from "./api"
import { ONBOARDING_QUERY_KEY } from "./queries"
import type {
  ActivatePayload,
  AutomationPatchPayload,
  CancelPayload,
  DataStartPatchPayload,
  IdentityPatchPayload,
  ModulesPatchPayload,
  OnboardingCreatePayload,
  RoutingPatchPayload,
  RoutingResetPayload,
  ServiceProfilePatchPayload,
  IntegrationsPatchPayload,
  ConnectIntegrationPayload,
} from "./types"

export function formatOnboardingError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return "Du saknar behörighet för denna åtgärd."
    if (error.status === 409) {
      const body = error.body
      if (body && typeof body === "object" && "detail" in body) {
        const detail = (body as { detail: unknown }).detail
        if (typeof detail === "object" && detail && "message" in detail) {
          return String((detail as { message: string }).message)
        }
        if (typeof detail === "string") return detail
      }
      return "Åtgärden kunde inte utföras på grund av en konflikt."
    }
    if (error.status === 422) return "Ogiltig begäran. Kontrollera fälten."
  }
  return "Åtgärden misslyckades. Försök igen."
}

function invalidateOnboarding(
  queryClient: ReturnType<typeof useQueryClient>,
  sessionId?: string,
) {
  queryClient.invalidateQueries({ queryKey: ONBOARDING_QUERY_KEY })
  if (sessionId) {
    queryClient.invalidateQueries({
      queryKey: [...ONBOARDING_QUERY_KEY, "session", sessionId],
    })
  }
  queryClient.invalidateQueries({ queryKey: TENANTS_QUERY_KEY })
}

function invalidateSlice2aSideEffects(
  queryClient: ReturnType<typeof useQueryClient>,
  sessionId: string,
) {
  invalidateOnboarding(queryClient, sessionId)
  queryClient.invalidateQueries({
    queryKey: [...ONBOARDING_QUERY_KEY, "activation-plan", sessionId],
  })
  queryClient.invalidateQueries({
    queryKey: [...ONBOARDING_QUERY_KEY, "routing", sessionId],
  })
}

function invalidateSlice2bSideEffects(
  queryClient: ReturnType<typeof useQueryClient>,
  sessionId: string,
) {
  invalidateSlice2aSideEffects(queryClient, sessionId)
  queryClient.invalidateQueries({
    queryKey: [...ONBOARDING_QUERY_KEY, "integrations", sessionId],
  })
  queryClient.invalidateQueries({
    queryKey: [...ONBOARDING_QUERY_KEY, "external-routing", sessionId],
  })
}

export function usePatchIntegrationsMutation(sessionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: IntegrationsPatchPayload) =>
      patchIntegrationsStep(sessionId, payload),
    onSuccess: () => invalidateSlice2bSideEffects(queryClient, sessionId),
  })
}

export function useConnectIntegrationMutation(sessionId: string) {
  return useMutation({
    mutationFn: (payload: ConnectIntegrationPayload & { integrationKey: string }) =>
      connectIntegrationStep(sessionId, payload.integrationKey, {
        version: payload.version,
        redirect_target: payload.redirect_target,
      }),
  })
}

export function useVerifyIntegrationMutation(sessionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: { integrationKey: string; version: number }) =>
      verifyIntegrationStep(sessionId, payload.integrationKey, payload.version),
    onSuccess: () => invalidateSlice2bSideEffects(queryClient, sessionId),
  })
}

export function usePatchExternalRoutingMutation(sessionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: import("./types").ExternalRoutingPatchPayload) =>
      patchExternalRoutingStep(sessionId, payload),
    onSuccess: () => invalidateSlice2bSideEffects(queryClient, sessionId),
  })
}

export function usePreviewExternalRoutingMutation(sessionId: string) {
  return useMutation({
    mutationFn: () => previewExternalRoutingStep(sessionId),
  })
}

export function useResetExternalRoutingMutation(sessionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: import("./types").ExternalRoutingResetPayload) =>
      resetExternalRoutingStep(sessionId, payload),
    onSuccess: () => invalidateSlice2bSideEffects(queryClient, sessionId),
  })
}

export function useUnrequestIntegrationMutation(sessionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: { integrationKey: string; version: number }) =>
      unrequestIntegrationStep(sessionId, payload.integrationKey, {
        version: payload.version,
      }),
    onSuccess: () => invalidateSlice2bSideEffects(queryClient, sessionId),
  })
}

export function useLocalUnlinkIntegrationMutation(sessionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: {
      integrationKey: string
      version: number
      reason: string
    }) =>
      localUnlinkIntegrationStep(sessionId, payload.integrationKey, {
        version: payload.version,
        reason: payload.reason,
      }),
    onSuccess: () => invalidateSlice2bSideEffects(queryClient, sessionId),
  })
}

export function useCreateOnboardingMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: OnboardingCreatePayload) => createOnboardingSession(payload),
    onSuccess: () => invalidateOnboarding(queryClient),
  })
}

export function usePatchIdentityMutation(sessionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: IdentityPatchPayload) =>
      patchOnboardingIdentity(sessionId, payload),
    onSuccess: () => invalidateOnboarding(queryClient, sessionId),
  })
}

export function usePatchModulesMutation(sessionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: ModulesPatchPayload) =>
      patchOnboardingModules(sessionId, payload),
    onSuccess: () => invalidateOnboarding(queryClient, sessionId),
  })
}

export function usePatchAutomationMutation(sessionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: AutomationPatchPayload) =>
      patchOnboardingAutomation(sessionId, payload),
    onSuccess: () => invalidateOnboarding(queryClient, sessionId),
  })
}

export function usePatchServiceProfileMutation(sessionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: ServiceProfilePatchPayload) =>
      patchServiceProfileStep(sessionId, payload),
    onSuccess: () => invalidateOnboarding(queryClient, sessionId),
  })
}

export function usePatchRoutingMutation(sessionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: RoutingPatchPayload) => patchRoutingStep(sessionId, payload),
    onSuccess: () => invalidateSlice2aSideEffects(queryClient, sessionId),
  })
}

export function usePreviewRoutingMutation(sessionId: string) {
  return useMutation({
    mutationFn: () => previewRoutingStep(sessionId),
  })
}

export function useResetRoutingMutation(sessionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: RoutingResetPayload) => resetRoutingStep(sessionId, payload),
    onSuccess: (data) => {
      invalidateSlice2aSideEffects(queryClient, sessionId)
      queryClient.setQueryData([...ONBOARDING_QUERY_KEY, "routing", sessionId], data)
    },
  })
}

export function usePatchDataStartMutation(sessionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: DataStartPatchPayload) => patchDataStartStep(sessionId, payload),
    onSuccess: () => invalidateOnboarding(queryClient, sessionId),
  })
}

export function useRunReadinessMutation(sessionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => runOnboardingReadiness(sessionId),
    onSuccess: () => invalidateOnboarding(queryClient, sessionId),
  })
}

export function useActivateOnboardingMutation(sessionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: ActivatePayload) =>
      activateOnboardingSession(sessionId, payload),
    onSuccess: () => invalidateOnboarding(queryClient, sessionId),
  })
}

export function useCancelOnboardingMutation(sessionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: CancelPayload) => cancelOnboardingSession(sessionId, payload),
    onSuccess: () => invalidateOnboarding(queryClient, sessionId),
  })
}
