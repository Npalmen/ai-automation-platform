import { ACTION_DOMAIN_TAB_MAP, RISK_DOMAINS } from "./constants"
import type { DomainPermissions, SettingsTab } from "./types"

export function resolveActionDomainTab(actionDomain: string | null | undefined): SettingsTab {
  if (!actionDomain) return "readiness"
  return ACTION_DOMAIN_TAB_MAP[actionDomain] ?? "readiness"
}

export function isRiskDomain(domain: string): boolean {
  return RISK_DOMAINS.has(domain)
}

export function canWriteDomain(
  permissions: Record<string, DomainPermissions> | undefined,
  domain: string,
): boolean {
  return Boolean(permissions?.[domain]?.write)
}

export function canPreviewDomain(
  permissions: Record<string, DomainPermissions> | undefined,
  domain: string,
): boolean {
  return Boolean(permissions?.[domain]?.preview)
}

export function parseTabParam(value: string | null): SettingsTab {
  const allowed = new Set([
    "identity",
    "modules",
    "integrations",
    "routing",
    "automation",
    "readiness",
  ])
  if (value && allowed.has(value)) {
    return value as SettingsTab
  }
  return "identity"
}
