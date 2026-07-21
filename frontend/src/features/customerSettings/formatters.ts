const READINESS_STATUS_LABELS: Record<string, string> = {
  ready: "Redo",
  ready_with_warnings: "Redo med varningar",
  not_ready: "Inte redo",
}

const SELECTION_STATUS_LABELS: Record<string, string> = {
  not_selected: "Ej aktuell",
  selected_optional: "Valfri",
  selected_required: "Obligatorisk",
}

const SUPPORT_STATUS_LABELS: Record<string, string> = {
  available: "Tillgänglig",
  coming_later: "Kommer senare",
  deprecated: "Utfasad",
}

const TENANT_STATUS_LABELS: Record<string, string> = {
  active: "Aktiv",
  inactive: "Inaktiv",
  archived: "Arkiverad",
}

const LIFECYCLE_STATUS_LABELS: Record<string, string> = {
  active: "Aktiv",
  onboarding: "Onboarding",
  draft: "Utkast",
  archived: "Arkiverad",
  waiting_for_customer: "Väntar på kund",
  technical_verification: "Teknisk verifiering",
  ready_for_activation: "Redo för aktivering",
}

const SCHEDULER_LABELS: Record<string, string> = {
  paused: "Pausad",
  manual: "Manuell",
  scheduled: "Schemalagd",
}

const AUTO_ACTION_LABELS: Record<string, string> = {
  manual: "Manuell",
  semi: "Semi-automatisk",
  auto: "Automatisk",
}

export function readinessStatusLabel(status: string): string {
  return READINESS_STATUS_LABELS[status] ?? "Okänd status"
}

export function selectionStatusLabel(status: string): string {
  return SELECTION_STATUS_LABELS[status] ?? "Okänd"
}

export function supportStatusLabel(status: string | null | undefined): string {
  if (!status) return "Okänd"
  return SUPPORT_STATUS_LABELS[status] ?? status
}

export function tenantStatusLabel(status: string): string {
  return TENANT_STATUS_LABELS[status] ?? status
}

export function lifecycleStatusLabel(status: string): string {
  return LIFECYCLE_STATUS_LABELS[status] ?? status
}

export function schedulerLabel(mode: string | null | undefined): string {
  if (!mode) return "Okänd"
  return SCHEDULER_LABELS[mode] ?? mode
}

export function autoActionLabel(value: string): string {
  return AUTO_ACTION_LABELS[value] ?? value
}

const ROLE_LABELS: Record<string, string> = {
  read_only: "Skrivskyddad",
  operations: "Operations",
  admin: "Administratör",
  super_admin: "Superadministratör",
}

export function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString("sv-SE")
}
