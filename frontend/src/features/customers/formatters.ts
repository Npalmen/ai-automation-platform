export function formatActivityAt(value: string | null | undefined): string {
  if (!value) {
    return "Ingen aktivitet"
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

export function tenantStatusLabel(status: string): string {
  if (status === "active") return "Aktiv"
  if (status === "inactive") return "Inaktiv"
  return "Okänd"
}

export function integrationSummaryLabel(key: string): string {
  const labels: Record<string, string> = {
    google_mail: "Gmail",
    gmail: "Gmail",
    visma: "Visma",
    google_sheets: "Google Sheets",
    monday: "Monday",
    fortnox: "Fortnox",
  }
  return labels[key] ?? key
}
