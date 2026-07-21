import { useState } from "react"
import { Link } from "react-router-dom"

import { StatusBadge } from "@/components/operator/StatusBadge"
import { Button } from "@/components/ui/button"
import type { FinanceDestinationStatus, VismaDisposition } from "./types"
import { usePatchIntegrationsMutation } from "./mutations"

type Props = {
  tenantId: string
  sessionId: string
  version: number
  canWrite: boolean
  status: FinanceDestinationStatus | undefined
}

const PROVIDERS = [
  { key: "visma" as const, label: "Visma", comingLater: false },
  { key: "fortnox" as const, label: "Fortnox", comingLater: true },
  { key: "bokio" as const, label: "Bokio", comingLater: true },
]

export function FinanceDestinationPanel({
  tenantId,
  sessionId,
  version,
  canWrite,
  status,
}: Props) {
  const patchMutation = usePatchIntegrationsMutation(sessionId)
  const [manualDialogOpen, setManualDialogOpen] = useState(false)
  const [pendingDisposition, setPendingDisposition] = useState<VismaDisposition>("not_selected")

  const active = status?.active_implementation ?? "none"
  const routingValid = status?.accounting_routing_valid ?? false

  const applyChoice = (choice: "visma" | "manual_accounting_routing", disposition?: VismaDisposition) => {
    void patchMutation.mutateAsync({
      version,
      finance_destination: {
        choice,
        visma_disposition: choice === "manual_accounting_routing" ? disposition : undefined,
      },
    })
  }

  return (
    <div className="rounded-lg border border-border bg-page p-4">
      <h4 className="text-body font-medium text-text-primary">Ekonomidestination</h4>
      <p className="mt-1 text-body-small text-text-secondary">
        Välj hur fakturahantering ska hanteras. Detta är separat från anslutning och verifiering
        nedan.
      </p>

      <fieldset className="mt-3 space-y-2">
        <legend className="sr-only">Ekonomidestination</legend>
        {PROVIDERS.map((provider) => (
          <label
            key={provider.key}
            className={`flex items-center gap-2 rounded-md border border-border px-3 py-2 ${
              provider.comingLater ? "opacity-60" : ""
            }`}
          >
            <input
              type="radio"
              name="finance-destination"
              value={provider.key}
              checked={active === provider.key}
              disabled={!canWrite || provider.comingLater || patchMutation.isPending}
              onChange={() => {
                if (provider.key === "visma") applyChoice("visma")
              }}
            />
            <span>{provider.label}</span>
            {provider.comingLater ? <StatusBadge variant="unknown" label="Kommer senare" /> : null}
          </label>
        ))}
        <label className="flex items-center gap-2 rounded-md border border-border px-3 py-2">
          <input
            type="radio"
            name="finance-destination"
            value="manual_accounting_routing"
            checked={active === "manual_accounting_routing"}
            disabled={!canWrite || patchMutation.isPending}
            onChange={() => {
              setPendingDisposition("not_selected")
              setManualDialogOpen(true)
            }}
          />
          <span>Manuell ekonomirouting</span>
        </label>
      </fieldset>

      {active === "manual_accounting_routing" ? (
        <div className="mt-3 space-y-2 rounded-md border border-border bg-surface-subtle p-3 text-body-small">
          <p>
            Routing-status:{" "}
            {routingValid ? (
              <StatusBadge variant="healthy" label="Giltig ekonomirouting" />
            ) : (
              <StatusBadge variant="warning" label="Saknar giltig ekonomirouting" />
            )}
          </p>
          {status?.accounting_routes?.length ? (
            <ul className="list-inside list-disc">
              {status.accounting_routes.map((route) => (
                <li key={route.service_type}>
                  {route.service_type} → {route.effective} ({route.source})
                </li>
              ))}
            </ul>
          ) : (
            <p>Ingen fakturarouting konfigurerad ännu.</p>
          )}
          {!routingValid ? (
            <p className="text-status-warning">
              Kräver minst en fakturatjänst med routing till finance eller invoice.
            </p>
          ) : null}
          <Link
            className="text-body-small font-medium text-text-primary underline"
            to={`/ops/customers/${tenantId}/onboarding?step=routing`}
          >
            Gå till Routing-steget
          </Link>
        </div>
      ) : null}

      {manualDialogOpen ? (
        <div
          className="mt-3 space-y-3 rounded-md border border-border bg-surface-subtle p-3"
          role="dialog"
          aria-labelledby="visma-disposition-title"
        >
          <h5 id="visma-disposition-title" className="text-body-small font-medium text-text-primary">
            Vad ska hända med Visma?
          </h5>
          <p className="text-body-small text-text-secondary">
            Visma-credential raderas inte. Välj hur Visma ska behandlas när manuell ekonomirouting
            används.
          </p>
          <label className="flex items-center gap-2 text-body-small">
            <input
              type="radio"
              name="visma-disposition"
              checked={pendingDisposition === "not_selected"}
              onChange={() => setPendingDisposition("not_selected")}
            />
            Ej aktuell
          </label>
          <label className="flex items-center gap-2 text-body-small">
            <input
              type="radio"
              name="visma-disposition"
              checked={pendingDisposition === "selected_optional"}
              onChange={() => setPendingDisposition("selected_optional")}
            />
            Valfri
          </label>
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              disabled={patchMutation.isPending}
              onClick={() => {
                applyChoice("manual_accounting_routing", pendingDisposition)
                setManualDialogOpen(false)
              }}
            >
              Bekräfta manuell ekonomirouting
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => setManualDialogOpen(false)}
            >
              Avbryt
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}
