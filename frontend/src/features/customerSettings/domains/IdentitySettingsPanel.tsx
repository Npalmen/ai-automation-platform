import { tenantStatusLabel } from "../formatters"

type Props = {
  value: Record<string, unknown>
  tenantStatus: string
  canWrite: boolean
  onChange: (next: Record<string, unknown>) => void
}

const TEXT_FIELDS = [
  { key: "name", label: "Företagsnamn" },
  { key: "primary_contact", label: "Primär kontakt" },
  { key: "contact_email", label: "Kontakt-e-post" },
  { key: "phone", label: "Telefon" },
  { key: "timezone", label: "Tidszon" },
  { key: "language", label: "Språk" },
  { key: "org_number", label: "Organisationsnummer" },
] as const

export function IdentitySettingsPanel({ value, tenantStatus, canWrite, onChange }: Props) {
  const company = (value.company as Record<string, unknown> | undefined) ?? value

  const updateCompany = (key: string, fieldValue: string) => {
    if (key === "name") {
      onChange({ ...value, name: fieldValue })
      return
    }
    onChange({
      ...value,
      company: {
        ...company,
        [key]: fieldValue,
      },
    })
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="text-caption text-text-secondary" htmlFor="identity-slug">
            Slug
          </label>
          <input
            id="identity-slug"
            className="mt-1 w-full rounded-md border border-border bg-page px-3 py-2 text-body"
            value={String(value.slug ?? "")}
            disabled
            readOnly
          />
          <p className="mt-1 text-caption text-text-secondary">Slug är skrivskyddad.</p>
        </div>
        <div>
          <label className="text-caption text-text-secondary" htmlFor="identity-status">
            Tenantstatus
          </label>
          <input
            id="identity-status"
            className="mt-1 w-full rounded-md border border-border bg-page px-3 py-2 text-body"
            value={tenantStatusLabel(tenantStatus)}
            disabled
            readOnly
          />
        </div>
      </div>

      {TEXT_FIELDS.map((field) => {
        const current =
          field.key === "name"
            ? String(value.name ?? "")
            : String(company[field.key] ?? "")
        return (
          <div key={field.key}>
            <label className="text-caption text-text-secondary" htmlFor={`identity-${field.key}`}>
              {field.label}
            </label>
            <input
              id={`identity-${field.key}`}
              className="mt-1 w-full rounded-md border border-border bg-surface px-3 py-2 text-body"
              value={current}
              disabled={!canWrite}
              onChange={(event) => updateCompany(field.key, event.target.value)}
            />
          </div>
        )
      })}
    </div>
  )
}
