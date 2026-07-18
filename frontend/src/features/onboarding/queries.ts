import { useQuery } from "@tanstack/react-query"

import { ApiError } from "@/api/client"

import {
  fetchActivationPlan,
  fetchDataStartStep,
  fetchOnboardingRegistries,
  fetchOnboardingSession,
  fetchOnboardingSessions,
  fetchOnboardingStep,
  fetchRoutingStep,
  fetchServiceProfileStep,
  fetchIntegrationsStep,
} from "./api"

export const ONBOARDING_QUERY_KEY = ["admin", "onboarding"] as const
export const ONBOARDING_REGISTRIES_KEY = [...ONBOARDING_QUERY_KEY, "registries"] as const

export function useOnboardingRegistriesQuery() {
  return useQuery({
    queryKey: ONBOARDING_REGISTRIES_KEY,
    queryFn: fetchOnboardingRegistries,
    staleTime: 300_000,
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 401) && count < 1,
  })
}

export function useActivationPlanQuery(sessionId: string | undefined, enabled = false) {
  return useQuery({
    queryKey: [...ONBOARDING_QUERY_KEY, "activation-plan", sessionId],
    queryFn: () => fetchActivationPlan(sessionId!),
    enabled: Boolean(sessionId && enabled),
    staleTime: 0,
  })
}

export function useOnboardingSessionsQuery(openOnly = true) {
  return useQuery({
    queryKey: [...ONBOARDING_QUERY_KEY, { openOnly }],
    queryFn: () => fetchOnboardingSessions(openOnly),
    staleTime: 15_000,
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 401) && count < 1,
  })
}

export function useOnboardingSessionQuery(sessionId: string | undefined) {
  return useQuery({
    queryKey: [...ONBOARDING_QUERY_KEY, "session", sessionId],
    queryFn: () => fetchOnboardingSession(sessionId!),
    enabled: Boolean(sessionId),
    staleTime: 10_000,
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 401) && count < 1,
  })
}

export function useOnboardingStepQuery(
  sessionId: string | undefined,
  stepKey: string | undefined,
  enabled = true,
) {
  return useQuery({
    queryKey: [...ONBOARDING_QUERY_KEY, "step", sessionId, stepKey],
    queryFn: () => fetchOnboardingStep(sessionId!, stepKey!),
    enabled: Boolean(sessionId && stepKey && enabled),
    staleTime: 10_000,
  })
}

export function useServiceProfileStepQuery(sessionId: string | undefined, enabled = false) {
  return useQuery({
    queryKey: [...ONBOARDING_QUERY_KEY, "service-profile", sessionId],
    queryFn: () => fetchServiceProfileStep(sessionId!),
    enabled: Boolean(sessionId && enabled),
    staleTime: 0,
  })
}

export function useRoutingStepQuery(sessionId: string | undefined, enabled = false) {
  return useQuery({
    queryKey: [...ONBOARDING_QUERY_KEY, "routing", sessionId],
    queryFn: () => fetchRoutingStep(sessionId!),
    enabled: Boolean(sessionId && enabled),
    staleTime: 0,
  })
}

export function useDataStartStepQuery(sessionId: string | undefined, enabled = false) {
  return useQuery({
    queryKey: [...ONBOARDING_QUERY_KEY, "data-start", sessionId],
    queryFn: () => fetchDataStartStep(sessionId!),
    enabled: Boolean(sessionId && enabled),
    staleTime: 0,
  })
}

export function useIntegrationsStepQuery(sessionId: string | undefined, enabled = false) {
  return useQuery({
    queryKey: [...ONBOARDING_QUERY_KEY, "integrations", sessionId],
    queryFn: () => fetchIntegrationsStep(sessionId!),
    enabled: Boolean(sessionId && enabled),
    staleTime: 0,
  })
}

export function findOpenSessionForTenant(
  sessions: { items: Array<{ tenant_id: string; id: string }> } | undefined,
  tenantId: string,
) {
  return sessions?.items.find((item) => item.tenant_id === tenantId)
}
