import type { PanelSeverity, SignalState } from "./types"

export function signalStateLabel(value: SignalState): string {
  if (value === "yes") return "Ja"
  if (value === "no") return "Nej"
  if (value === "not_applicable") return "Ej tillämpligt"
  return "Okänt"
}

export function panelSeverityLabel(value: PanelSeverity): string {
  if (value === "critical") return "Kritiskt"
  if (value === "failed") return "Fel"
  if (value === "warning") return "Varning"
  return "Information"
}

export function formatDetectedAt(value: string | null | undefined): string {
  if (!value) {
    return "Okänt"
  }
  try {
    return new Intl.DateTimeFormat("sv-SE", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value))
  } catch {
    return value
  }
}

export function formatAgeHours(hours: number | null | undefined): string {
  if (hours == null) {
    return "Okänt"
  }
  return `${hours} h`
}

export function categoryLabel(category: string): string {
  const labels: Record<string, string> = {
    integration: "Integration",
    integration_event: "Integrationshändelse",
    integration_reconciliation: "Avstämning",
    pipeline: "Pipeline",
    approval: "Godkännande",
    approval_email: "E-postgodkännande",
    approval_dispatch: "Dispatch-godkännande",
    scheduler: "Scheduler",
    inbox_sync: "Inkorgssynk",
    oauth: "OAuth",
    tenant_config: "Tenantkonfiguration",
  }
  return labels[category] ?? category
}
