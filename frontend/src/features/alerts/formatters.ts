import type { AlertSeverity, AlertStatus, SeverityBadge } from "./types"

export function alertSeverityBadge(severity: AlertSeverity): SeverityBadge {
  switch (severity) {
    case "critical":
      return "P1"
    case "high":
      return "P2"
    case "warning":
      return "P3"
    default:
      return "P4"
  }
}

export function alertSeverityLabel(severity: AlertSeverity): string {
  switch (severity) {
    case "critical":
      return "Kritisk"
    case "high":
      return "Hög"
    case "warning":
      return "Varning"
    default:
      return "Information"
  }
}

export function alertStatusLabel(status: AlertStatus): string {
  switch (status) {
    case "open":
      return "Öppen"
    case "acknowledged":
      return "Bekräftad"
    case "snoozed":
      return "Snoozad"
    case "resolved":
      return "Löst"
    case "suppressed":
      return "Undertryckt"
    default:
      return status
  }
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString("sv-SE", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export function formatAgeHours(hours: number | null | undefined): string {
  if (hours == null) return "—"
  if (hours < 1) return "< 1 h"
  if (hours < 24) return `${hours} h`
  const days = Math.floor(hours / 24)
  const rem = hours % 24
  return rem > 0 ? `${days} d ${rem} h` : `${days} d`
}

export function isAlertWritable(status: AlertStatus): boolean {
  return status === "open" || status === "acknowledged" || status === "snoozed"
}
