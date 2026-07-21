import type { SettingsTab } from "./types"

export const SETTINGS_TABS: Array<{ id: SettingsTab; label: string }> = [
  { id: "identity", label: "Företagsuppgifter" },
  { id: "modules", label: "Tjänster och moduler" },
  { id: "integrations", label: "Integrationer" },
  { id: "routing", label: "Routing" },
  { id: "automation", label: "Automation och säkerhet" },
  { id: "readiness", label: "Readiness" },
]

export const RISK_DOMAINS = new Set(["modules", "integrations", "routing", "automation"])

export const ACTION_DOMAIN_TAB_MAP: Record<string, SettingsTab> = {
  identity: "identity",
  modules: "modules",
  services: "modules",
  integrations: "integrations",
  finance_destination: "integrations",
  routing: "routing",
  automation: "automation",
  intake: "modules",
  readiness: "readiness",
}
