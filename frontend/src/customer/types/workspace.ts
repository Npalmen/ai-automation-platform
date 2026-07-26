export type CustomerRole = "customer_viewer"

export type WorkspaceMode = "mock" | "preview"

export type FeatureFlags = {
  customer_workspace_writes: boolean
  connected_api: boolean
  preview_mode: boolean
}

export const DEFAULT_FEATURE_FLAGS: FeatureFlags = {
  customer_workspace_writes: false,
  connected_api: false,
  preview_mode: true,
}

export type WorkspaceContext = {
  tenant_id: string
  company_name: string
  contact_name: string
  contact_email: string
  support_email: string
  language: string
  region: string
  workspace_mode: WorkspaceMode
  feature_flags: FeatureFlags
}

export type CustomerAuthState = {
  role: CustomerRole
  mode: WorkspaceMode
  connected: false
  context: WorkspaceContext
}
