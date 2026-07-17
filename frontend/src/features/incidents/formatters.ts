import type { IncidentStatus, PanelSeverity } from "./types"

const SEVERITY_LABELS: Record<PanelSeverity, string> = {
  critical: "Kritisk",
  failed: "Fel",
  warning: "Varning",
  information: "Information",
}

const STATUS_LABELS: Record<IncidentStatus, string> = {
  open: "Öppen",
  acknowledged: "Bekräftad",
  investigating: "Utreds",
  monitoring: "Övervakas",
  resolved: "Löst",
  closed: "Stängd",
}

export function panelSeverityLabel(severity: PanelSeverity): string {
  return SEVERITY_LABELS[severity] ?? severity
}

export function incidentStatusLabel(status: IncidentStatus): string {
  return STATUS_LABELS[status] ?? status
}

export function formatAgeHours(hours: number | null | undefined): string {
  if (hours == null) return "—"
  if (hours < 1) return "< 1 h"
  if (hours < 24) return `${hours} h`
  const days = Math.floor(hours / 24)
  return `${days} d`
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "—"
  try {
    return new Date(value).toLocaleString("sv-SE")
  } catch {
    return value
  }
}

export function isIncidentWritable(status: IncidentStatus): boolean {
  return status !== "closed"
}

export function parseStatusActionId(actionId: string): IncidentStatus | null {
  if (!actionId.startsWith("incident.status.")) return null
  return actionId.replace("incident.status.", "") as IncidentStatus
}
