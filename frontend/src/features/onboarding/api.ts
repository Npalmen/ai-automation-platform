import { get, patchJson, postJson } from "@/api/client"

import type {
  ActivatePayload,
  ActivationPlan,
  AutomationPatchPayload,
  CancelPayload,
  DataStartPatchPayload,
  IdentityPatchPayload,
  ModulesPatchPayload,
  OnboardingCreatePayload,
  OnboardingListResponse,
  OnboardingRegistriesResponse,
  OnboardingSession,
  ReadinessResult,
  RoutingPatchPayload,
  RoutingPreviewResponse,
  RoutingResetPayload,
  ServiceProfilePatchPayload,
  Slice2aStepResponse,
  StepDetail,
  IntegrationsStepResponse,
  IntegrationsPatchPayload,
  ExternalRoutingPatchPayload,
  ExternalRoutingResetPayload,
  ConnectIntegrationPayload,
  IntegrationActionPayload,
  IntegrationLifecycleItem,
} from "./types"

export function fetchOnboardingRegistries(): Promise<OnboardingRegistriesResponse> {
  return get<OnboardingRegistriesResponse>("/admin/onboarding/registries")
}

export function fetchActivationPlan(sessionId: string): Promise<ActivationPlan> {
  return get<ActivationPlan>(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/activation-plan`,
  )
}

export function fetchOnboardingSessions(openOnly = true): Promise<OnboardingListResponse> {
  const params = new URLSearchParams({ open_only: String(openOnly) })
  return get<OnboardingListResponse>(`/admin/onboarding?${params}`)
}

export function fetchOnboardingSession(sessionId: string): Promise<OnboardingSession> {
  return get<OnboardingSession>(`/admin/onboarding/${encodeURIComponent(sessionId)}`)
}

export function createOnboardingSession(body: OnboardingCreatePayload): Promise<OnboardingSession> {
  return postJson<OnboardingSession>("/admin/onboarding", body)
}

export function patchOnboardingIdentity(
  sessionId: string,
  body: IdentityPatchPayload,
): Promise<OnboardingSession> {
  return patchJson<OnboardingSession>(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/identity`,
    body,
  )
}

export function patchOnboardingModules(
  sessionId: string,
  body: ModulesPatchPayload,
): Promise<OnboardingSession> {
  return patchJson<OnboardingSession>(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/modules`,
    body,
  )
}

export function patchOnboardingAutomation(
  sessionId: string,
  body: AutomationPatchPayload,
): Promise<OnboardingSession> {
  return patchJson<OnboardingSession>(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/automation`,
    body,
  )
}

export function fetchOnboardingStep(
  sessionId: string,
  stepKey: string,
): Promise<StepDetail> {
  return get<StepDetail>(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/steps/${encodeURIComponent(stepKey)}`,
  )
}

export function fetchServiceProfileStep(sessionId: string): Promise<Slice2aStepResponse> {
  return get<Slice2aStepResponse>(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/service-profile`,
  )
}

export function patchServiceProfileStep(
  sessionId: string,
  body: ServiceProfilePatchPayload,
): Promise<OnboardingSession> {
  return patchJson<OnboardingSession>(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/service-profile`,
    body,
  )
}

export function fetchRoutingStep(sessionId: string): Promise<Slice2aStepResponse> {
  return get<Slice2aStepResponse>(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/routing`,
  )
}

export function patchRoutingStep(
  sessionId: string,
  body: RoutingPatchPayload,
): Promise<OnboardingSession> {
  return patchJson<OnboardingSession>(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/routing`,
    body,
  )
}

export function previewRoutingStep(sessionId: string): Promise<RoutingPreviewResponse> {
  return postJson<RoutingPreviewResponse>(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/routing-preview`,
    {},
  )
}

export function resetRoutingStep(
  sessionId: string,
  body: RoutingResetPayload,
): Promise<Slice2aStepResponse> {
  return postJson<Slice2aStepResponse>(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/routing-reset`,
    body,
  )
}

export function fetchDataStartStep(sessionId: string): Promise<Slice2aStepResponse> {
  return get<Slice2aStepResponse>(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/data-start`,
  )
}

export function patchDataStartStep(
  sessionId: string,
  body: DataStartPatchPayload,
): Promise<OnboardingSession> {
  return patchJson<OnboardingSession>(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/data-start`,
    body,
  )
}

export function runOnboardingReadiness(sessionId: string): Promise<ReadinessResult> {
  return postJson<ReadinessResult>(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/readiness`,
    {},
  )
}

export function activateOnboardingSession(
  sessionId: string,
  body: ActivatePayload,
): Promise<{ status: string; tenant_id: string; session_id: string; message: string }> {
  return postJson(`/admin/onboarding/${encodeURIComponent(sessionId)}/activate`, body)
}

export function cancelOnboardingSession(
  sessionId: string,
  body: CancelPayload,
): Promise<OnboardingSession> {
  return postJson<OnboardingSession>(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/cancel`,
    body,
  )
}

export function fetchIntegrationsStep(sessionId: string): Promise<IntegrationsStepResponse> {
  return get<IntegrationsStepResponse>(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/integrations`,
  )
}

export function patchIntegrationsStep(
  sessionId: string,
  body: IntegrationsPatchPayload,
): Promise<OnboardingSession> {
  return patchJson<OnboardingSession>(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/integrations`,
    body,
  )
}

export function connectIntegrationStep(
  sessionId: string,
  integrationKey: string,
  body: ConnectIntegrationPayload,
): Promise<{ authorization_url: string }> {
  return postJson(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/integrations/${encodeURIComponent(integrationKey)}/connect`,
    body,
  )
}

export function verifyIntegrationStep(
  sessionId: string,
  integrationKey: string,
  version: number,
): Promise<IntegrationLifecycleItem> {
  return postJson(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/integrations/${encodeURIComponent(integrationKey)}/verify`,
    { version },
  )
}

export function fetchExternalRoutingStep(sessionId: string) {
  return get(`/admin/onboarding/${encodeURIComponent(sessionId)}/external-routing`)
}

export function patchExternalRoutingStep(
  sessionId: string,
  body: ExternalRoutingPatchPayload,
): Promise<OnboardingSession> {
  return patchJson<OnboardingSession>(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/external-routing`,
    body,
  )
}

export function previewExternalRoutingStep(sessionId: string): Promise<RoutingPreviewResponse> {
  return postJson<RoutingPreviewResponse>(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/external-routing-preview`,
    {},
  )
}

export function resetExternalRoutingStep(
  sessionId: string,
  body: ExternalRoutingResetPayload,
): Promise<OnboardingSession> {
  return postJson<OnboardingSession>(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/external-routing-reset`,
    body,
  )
}

export function unrequestIntegrationStep(
  sessionId: string,
  integrationKey: string,
  body: IntegrationActionPayload,
): Promise<OnboardingSession> {
  return postJson<OnboardingSession>(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/integrations/${encodeURIComponent(integrationKey)}/unrequest`,
    body,
  )
}

export function localUnlinkIntegrationStep(
  sessionId: string,
  integrationKey: string,
  body: IntegrationActionPayload,
): Promise<OnboardingSession> {
  return postJson<OnboardingSession>(
    `/admin/onboarding/${encodeURIComponent(sessionId)}/integrations/${encodeURIComponent(integrationKey)}/local-unlink`,
    body,
  )
}
