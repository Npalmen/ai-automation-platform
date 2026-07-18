export type StepStatus =
  | "not_started"
  | "in_progress"
  | "blocked"
  | "completed"
  | "not_applicable"
  | "not_implemented"

export type OverallReadinessStatus =
  | "not_ready"
  | "ready_with_warnings"
  | "ready"
  | "unknown"

export type OnboardingStepState = {
  step_key: string
  step_status: StepStatus
  verification_level: string
  blocking_issues: Array<Record<string, unknown>>
  warnings: Array<Record<string, unknown>>
  blocks_activation: boolean
  read_only: boolean
  read_only_reason: string | null
}

export type OnboardingSession = {
  id: string
  tenant_id: string
  status: string
  current_step: string
  version: number
  readiness_check_version: number
  created_at: string
  updated_at: string
  activated_at: string | null
  company_name: string | null
  slug: string | null
  capabilities: string[]
  integrations: string[]
  preset_key: string | null
  preset_version: number | null
  legacy_capability_keys: string[]
  legacy_preset: boolean
  steps: OnboardingStepState[]
}

export type OnboardingListResponse = {
  items: OnboardingSession[]
}

export type ReadinessCheckItem = {
  id: string
  message: string
  source_class: string
  step_key?: string | null
}

export type ReadinessResult = {
  overall_status: OverallReadinessStatus
  check_version: number
  blocking_checks: ReadinessCheckItem[]
  warnings: ReadinessCheckItem[]
  passed_checks: ReadinessCheckItem[]
  not_applicable: ReadinessCheckItem[]
  not_verifiable: ReadinessCheckItem[]
  last_checked_at: string
}

export type StepDetail = {
  step_key: string
  step_status: StepStatus
  verification_level: string
  blocks_activation: boolean
  read_only: boolean
  read_only_reason: string | null
  details: Record<string, unknown>
}

export type RegistryCapability = {
  key: string
  label: string
  description: string
  availability: string
  supported_in_current_slice: boolean
  dependencies: { integrations?: string[]; runtime?: string[] }
  requires_api_key: boolean
}

export type RegistryIntegration = {
  key: string
  label: string
  description: string
  availability: string
  supported_in_current_slice: boolean
  verification_capability?: string | null
  lifecycle_cap?: string | null
  limitation_ids?: string[]
}

export type RegistryExternalRoutingTarget = {
  key: string
  label: string
  job_type: string
  integration_key: string
  enforced: boolean
  availability: string
  supported_in_current_slice: boolean
}

export type RegistryAutomationPreset = {
  key: string
  version: number
  label: string
  description: string
  availability: string
  supported_in_current_slice: boolean
  activation_allows_scheduler: boolean
  scheduler_run_mode: string
  limitation?: string | null
}

export type OnboardingRegistriesResponse = {
  registry_schema_version: number
  registry_revision: string
  product_capabilities: RegistryCapability[]
  integrations: RegistryIntegration[]
  runtime_features: Array<{
    key: string
    label: string
    description: string
    availability: string
    supported_in_current_slice: boolean
    activation_note?: string | null
  }>
  automation_presets: RegistryAutomationPreset[]
  service_profiles: RegistryServiceProfile[]
  lead_field_registry: Array<{ key: string; label: string }>
  routing_destinations: Array<{ key: string; label: string }>
  data_start_modes: Array<{
    key: string
    label: string
    description: string
    availability: string
    supported_in_current_slice: boolean
    recommended?: boolean
  }>
  service_type_lead_type_map_version: number
  external_routing_targets?: RegistryExternalRoutingTarget[]
}

export type RegistryServiceProfile = {
  key: string
  label: string
  description: string
  category: string
  default_route: string
  availability: string
  supported_in_current_slice: boolean
  required_fields_summary: string[]
  optional_fields_summary: string[]
}

export type Slice2aStepResponse = {
  step_key: string
  step_status: StepStatus
  verification_level: string
  blocks_activation: boolean
  draft: Record<string, unknown>
  effective: Record<string, unknown>
}

export type ServiceProfilePatchPayload = {
  version: number
  selected_profiles: string[]
  lead_requirements: Record<string, Record<string, "required" | "optional" | "inherit">>
}

export type RoutingPatchPayload = {
  version: number
  route_overrides: Record<string, string | null>
}

export type DataStartPatchPayload = {
  version: number
  mode: "new_incoming_only"
}

export type EffectiveRouteRow = {
  service_type: string
  platform_default: string
  override: string | null
  effective: string
  source: string
}

export type RoutingPreviewRow = {
  service_type: string
  effective_route: string
  source: string
  manual_review: boolean
}

export type RoutingPreviewResponse = {
  preview: RoutingPreviewRow[]
  mutated: boolean
}

export type RoutingResetPayload = {
  version: number
  service_types: string[]
}

export type ActivationPlan = {
  plan_id: string
  plan_hash: string
  session_version: number
  readiness_check_version: number
  registry_revision: string
  registry_schema_version: number
  warning_ids: string[]
  consequences: Array<{ id: string; message: string; severity: string }>
  capability_states: Array<{
    capability_key: string
    lifecycle_state: string
    selected: boolean
    configured: boolean
    activated: boolean
    running: boolean
    message: string
  }>
  runtime_effects: Array<{
    feature_key: string
    status: string
    configured: boolean
    running: boolean
    message: string
  }>
}

export type OnboardingCreatePayload = {
  company_name: string
  slug: string
  org_number?: string
  contact_email?: string
  primary_contact?: string
  phone?: string
  timezone?: string
  language?: string
}

export type IdentityPatchPayload = {
  version: number
  company_name?: string
  slug?: string
  org_number?: string
  contact_email?: string
  primary_contact?: string
  phone?: string
  timezone?: string
  language?: string
}

export type ModulesPatchPayload = {
  version: number
  capabilities: string[]
  integrations: string[]
}

export type AutomationPatchPayload = {
  version: number
  preset_key: string
  preset_version: number
}

export type ActivatePayload = {
  version: number
  readiness_check_version: number
  plan_hash: string
  reason: string
  confirmation_phrase: string
  acknowledged_warning_ids: string[]
}

export type CancelPayload = {
  version: number
  reason: string
}

export type IntegrationLifecycleItem = {
  integration_key: string
  label: string
  lifecycle_status: string
  connection_status?: string
  verified: boolean
  connected: boolean
  configured: boolean
  required: boolean
  requested?: boolean
  verification_status?: string
  verified_at?: string | null
  freshness_max_hours?: number | null
  verification_error_code?: string | null
  source_class: string
  platform_credential?: boolean
  gmail_classification?: {
    label_query?: string | null
    platform_credential?: string
    tenant_mailbox_access?: string
    live_intake?: string
    capability_operational?: boolean
  } | null
}

export type IntegrationsStepResponse = {
  step_key: string
  step_status: StepStatus
  verification_level: string
  blocks_activation: boolean
  integration_state_revision: number
  draft: Record<string, unknown>
  integrations: IntegrationLifecycleItem[]
  details: Record<string, unknown>
}

export type IntegrationsPatchPayload = {
  version: number
  requested_integrations: string[]
  gmail?: { requested: boolean; label_scope_slug: string }
  visma?: { requested: boolean }
  google_sheets?: { requested: boolean; spreadsheet_id: string; export_tabs: string[] }
  monday?: { requested: boolean }
}

export type ExternalRoutingResetPayload = {
  version: number
  job_types: string[]
}

export type IntegrationActionPayload = {
  version: number
  reason?: string
}

export type ExternalRoutingPatchPayload = {
  version: number
  targets: Record<
    string,
    {
      target_type: "monday_board"
      board_id: string
      board_name: string
      group_id?: string | null
      group_name?: string | null
    }
  >
}

export type ConnectIntegrationPayload = {
  version: number
  redirect_target: string
}

export const WIZARD_STEPS = [
  { key: "identity", label: "Identitet" },
  { key: "modules", label: "Moduler" },
  { key: "automation", label: "Automation" },
  { key: "service_profile", label: "Serviceprofil" },
  { key: "routing", label: "Routing" },
  { key: "integrations", label: "Integrationer" },
  { key: "data_start", label: "Startläge" },
  { key: "readiness", label: "Readiness" },
  { key: "review", label: "Aktivera" },
] as const
