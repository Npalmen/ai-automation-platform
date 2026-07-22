import { StatusBadge } from "@/components/operator/StatusBadge"

import { selectionStatusLabel, supportStatusLabel } from "../formatters"
import type { CustomerSettingsAggregate } from "../types"

type Props = {
  data: CustomerSettingsAggregate
  draftSelections: Record<string, { selection_status: string; migration_review_required?: boolean }>
  financeChoice: "visma" | "manual_accounting_routing" | "none"
  vismaDisposition: "not_selected" | "selected_optional" | null
  manualDialogOpen: boolean
  canWrite: boolean
  onSelectionChange: (integrationKey: string, status: string) => void
  onFinanceChoice: (choice: "visma" | "manual_accounting_routing") => void
  onVismaDisposition: (value: "not_selected" | "selected_optional") => void
  onManualDialogOpen: (open: boolean) => void
}

const COMING_LATER = new Set(["fortnox", "bokio"])

export function IntegrationsSettingsPanel({
  data,
  draftSelections,
  financeChoice,
  vismaDisposition,
  manualDialogOpen,
  canWrite,
  onSelectionChange,
  onFinanceChoice,
  onVismaDisposition,
  onManualDialogOpen,
}: Props) {
  const finance = data.integration_group_status.finance_destination as Record<string, unknown>
  const routingValid = Boolean(finance.accounting_routing_valid)

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-border bg-page p-4">
        <h3 className="text-body font-medium text-text-primary">Ekonomidestination</h3>
        <fieldset className="mt-3 space-y-2">
          <legend className="sr-only">Ekonomidestination</legend>
          <label className="flex min-h-11 items-center gap-2 rounded-md border border-border px-3 py-2">
            <input
              type="radio"
              name="finance-destination"
              checked={financeChoice === "visma"}
              disabled={!canWrite}
              onChange={() => onFinanceChoice("visma")}
            />
            <span>Visma</span>
          </label>
          {["fortnox", "bokio"].map((provider) => (
            <label
              key={provider}
              className="flex min-h-11 items-center gap-2 rounded-md border border-border px-3 py-2 opacity-60"
            >
              <input type="radio" disabled />
              <span className="capitalize">{provider}</span>
              <StatusBadge variant="unknown" label="Kommer senare" />
            </label>
          ))}
          <label className="flex min-h-11 items-center gap-2 rounded-md border border-border px-3 py-2">
            <input
              type="radio"
              name="finance-destination"
              checked={financeChoice === "manual_accounting_routing"}
              disabled={!canWrite}
              onChange={() => onManualDialogOpen(true)}
            />
            <span>Manuell ekonomirouting</span>
          </label>
        </fieldset>

        {financeChoice === "manual_accounting_routing" ? (
          <div className="mt-3 space-y-2 rounded-md border border-border bg-surface-subtle p-3 text-body-small">
            <p>
              Routing-status:{" "}
              {routingValid ? (
                <StatusBadge variant="healthy" label="Giltig ekonomirouting" />
              ) : (
                <StatusBadge variant="warning" label="Saknar giltig ekonomirouting" />
              )}
            </p>
            <p className="text-text-secondary">
              Visma-credentials bevaras alltid. Välj disposition vid manuell routing.
            </p>
            {!routingValid ? (
              <p className="text-status-warning">
                Gå till Routing-fliken för att konfigurera fakturarouting till finance eller invoice.
              </p>
            ) : null}
          </div>
        ) : null}

        {manualDialogOpen ? (
          <div className="mt-3 space-y-3 rounded-md border border-border bg-surface-subtle p-3">
            <h4 className="text-body-small font-medium text-text-primary">Vad ska hända med Visma?</h4>
            <label className="flex items-center gap-2 text-body-small">
              <input
                type="radio"
                name="visma-disposition"
                checked={vismaDisposition === "not_selected"}
                onChange={() => onVismaDisposition("not_selected")}
              />
              Ej aktuell
            </label>
            <label className="flex items-center gap-2 text-body-small">
              <input
                type="radio"
                name="visma-disposition"
                checked={vismaDisposition === "selected_optional"}
                onChange={() => onVismaDisposition("selected_optional")}
              />
              Valfri
            </label>
            <div className="flex gap-2">
              <button
                type="button"
                className="rounded-md bg-primary px-3 py-2 text-label text-primary-foreground"
                disabled={!canWrite || !vismaDisposition}
                onClick={() => {
                  onFinanceChoice("manual_accounting_routing")
                  onManualDialogOpen(false)
                }}
              >
                Bekräfta manuell ekonomirouting
              </button>
              <button
                type="button"
                className="rounded-md border border-border px-3 py-2 text-label"
                onClick={() => onManualDialogOpen(false)}
              >
                Avbryt
              </button>
            </div>
          </div>
        ) : null}
      </section>

      <section>
        <h3 className="text-body font-medium text-text-primary">Integrationer</h3>
        <ul className="mt-3 space-y-3">
          {data.integration_selection_view.map((item) => {
            const draft = draftSelections[item.integration_key]
            const status = draft?.selection_status ?? item.selection_status
            const comingLater = COMING_LATER.has(item.integration_key) || item.support_status === "coming_later"
            return (
              <li
                key={item.integration_key}
                className={`rounded-md border border-border bg-page p-3 ${comingLater ? "opacity-60" : ""}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-body font-medium text-text-primary">{item.display_name_sv}</p>
                  <StatusBadge variant="unknown" label={supportStatusLabel(item.support_status)} />
                </div>
                <label className="mt-2 block text-caption text-text-secondary" htmlFor={`sel-${item.integration_key}`}>
                  Urval
                </label>
                <select
                  id={`sel-${item.integration_key}`}
                  className="mt-1 w-full rounded-md border border-border bg-surface px-3 py-2 text-body"
                  value={status}
                  disabled={!canWrite || comingLater || !item.selectable}
                  onChange={(event) => onSelectionChange(item.integration_key, event.target.value)}
                >
                  <option value="not_selected">{selectionStatusLabel("not_selected")}</option>
                  <option value="selected_optional">{selectionStatusLabel("selected_optional")}</option>
                  <option value="selected_required">{selectionStatusLabel("selected_required")}</option>
                </select>
                {item.migration_review_required ? (
                  <p className="mt-2 text-body-small text-status-warning">Migreringsgranskning krävs</p>
                ) : null}
              </li>
            )
          })}
        </ul>
      </section>
    </div>
  )
}
