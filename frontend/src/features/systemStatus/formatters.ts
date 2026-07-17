import type { FreshnessLevel, SystemStatusLevel } from "./types"
import type { StatusVariant } from "@/design/types"

export function toStatusVariant(status: SystemStatusLevel): StatusVariant {
  if (status === "not_configured") {
    return "unknown"
  }
  return status
}

export function statusLabel(status: SystemStatusLevel): string {
  const labels: Record<SystemStatusLevel, string> = {
    healthy: "Frisk",
    warning: "Varning",
    failed: "Fel",
    critical: "Kritiskt",
    paused: "Pausad",
    unknown: "Okänd",
    not_configured: "Ej konfigurerad",
  }
  return labels[status]
}

export function freshnessLabel(freshness: FreshnessLevel | null | undefined): string {
  if (!freshness) return "—"
  const labels: Record<FreshnessLevel, string> = {
    reported: "Rapporterad",
    stale: "Gammal",
    not_reported: "Ej rapporterad",
  }
  return labels[freshness]
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "—"
  return date.toLocaleString("sv-SE")
}

export function formatBuildTime(value: string | null | undefined): string {
  if (!value) return "Okänd"
  return `${formatTimestamp(value)} (byggtid)`
}

export function formatDeployTime(value: string | null | undefined): string {
  if (!value) return "Okänd deploytid"
  return formatTimestamp(value)
}

export function verificationLabel(
  value: string | null | undefined,
): string {
  const labels: Record<string, string> = {
    success: "Verifierad",
    failed: "Misslyckad",
    not_performed: "Ej utförd",
    unknown: "Okänd",
  }
  return labels[value ?? ""] ?? "Okänd"
}
