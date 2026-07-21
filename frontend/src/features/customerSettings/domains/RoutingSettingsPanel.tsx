type Props = {
  routing: Record<string, unknown>
  canWrite: boolean
  onChange: (routing: Record<string, unknown>) => void
}

const ROUTE_OPTIONS = [
  { value: "finance", label: "Ekonomi" },
  { value: "invoice", label: "Faktura" },
  { value: "support", label: "Support" },
  { value: "manual_review", label: "Manuell granskning" },
]

export function RoutingSettingsPanel({ routing, canWrite, onChange }: Props) {
  const overrides =
    (routing.route_overrides as Record<string, string> | undefined) ?? {}
  const invoiceRoute = overrides.invoice_generic ?? ""

  const updateInvoiceRoute = (value: string) => {
    onChange({
      ...routing,
      route_overrides: {
        ...overrides,
        invoice_generic: value,
      },
    })
  }

  return (
    <div className="space-y-4">
      <p className="text-body-small text-text-secondary">
        Konfigurera intern routing för fakturatjänster. För manuell ekonomirouting krävs destination finance
        eller invoice.
      </p>
      <div>
        <label className="text-caption text-text-secondary" htmlFor="routing-invoice-generic">
          invoice_generic
        </label>
        <select
          id="routing-invoice-generic"
          className="mt-1 w-full rounded-md border border-border bg-surface px-3 py-2 text-body"
          value={invoiceRoute}
          disabled={!canWrite}
          onChange={(event) => updateInvoiceRoute(event.target.value)}
        >
          <option value="">Välj routing</option>
          {ROUTE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  )
}
