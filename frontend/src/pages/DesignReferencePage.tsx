import { useState } from "react"

import { ActionDialog } from "@/components/operator/ActionDialog"
import { CriticalActionDialog } from "@/components/operator/CriticalActionDialog"
import { EmptyState } from "@/components/operator/EmptyState"
import { ErrorState } from "@/components/operator/ErrorState"
import { HealthIndicator } from "@/components/operator/HealthIndicator"
import { LoadingState } from "@/components/operator/LoadingState"
import { MetricCard } from "@/components/operator/MetricCard"
import { PageHeader } from "@/components/operator/PageHeader"
import { SeverityBadge } from "@/components/operator/SeverityBadge"
import { StatusBadge } from "@/components/operator/StatusBadge"
import { Button } from "@/components/ui/button"
import { getDesignContracts } from "@/design/loadContracts"

const DEMO_QUEUE = [
  {
    tenant: "TENANT_1001",
    problem: "Gmail har inte hämtat nya mejl sedan 08:42",
    time: "08:42",
    impact: "3 kunder påverkade",
    severity: "P2" as const,
    action: "Granska integration",
  },
  {
    tenant: "TENANT_2044",
    problem: "Visma-export väntar på manuell kontroll",
    time: "09:15",
    impact: "1 kund påverkad",
    severity: "P3" as const,
    action: "Öppna kö",
  },
]

const DEMO_RESOURCES = [
  { name: "Acme AB", status: "healthy" as const, detail: "Senaste backup lyckades" },
  { name: "Nordic Logistics", status: "warning" as const, detail: "Gmail-synk försenad" },
]

export function DesignReferencePage() {
  const contracts = getDesignContracts()
  const [actionOpen, setActionOpen] = useState(false)
  const [criticalOpen, setCriticalOpen] = useState(false)

  return (
    <div className="mx-auto flex min-w-0 max-w-content flex-col gap-8 px-4 py-6 md:px-6 lg:px-8">
      <PageHeader
        title="Designreferens"
        description="Designreferens — exempeldata. Ingen riktig driftdata eller API-anrop."
        status={<StatusBadge variant="unknown" label="Referens" />}
        actions={
          <Button type="button" variant="outline" onClick={() => setActionOpen(true)}>
            Testa dialog
          </Button>
        }
      />

      <section className="min-w-0 space-y-3">
        <h2 className="text-section-title text-text-primary">Profil</h2>
        <p className="text-body text-text-secondary">
          {contracts.uiProfile.profile.name} v{contracts.uiProfile.profile.version} —{" "}
          {contracts.uiProfile.profile.locale}
        </p>
      </section>

      <section className="min-w-0 space-y-4">
        <h2 className="text-section-title text-text-primary">Färger och typografi</h2>
        <div className="grid min-w-0 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ["page", "bg-page"],
            ["surface", "bg-surface"],
            ["brand", "bg-brand"],
            ["success", "bg-status-success"],
          ].map(([label, className]) => (
            <div
              key={label}
              className={`min-h-[4rem] rounded-lg border border-border p-3 ${className}`}
            >
              <p className="text-label text-text-primary">{label}</p>
            </div>
          ))}
        </div>
        <div className="space-y-2">
          <p className="text-display text-text-primary">Display</p>
          <p className="text-page-title text-text-primary">Sidtitel</p>
          <p className="text-section-title text-text-primary">Sektionsrubrik</p>
          <p className="text-body text-text-secondary">Brödtext för operatörer.</p>
          <p className="font-mono text-code text-text-muted">
            TENANT_1001-LONG-IDENTIFIER-EXAMPLE-2026
          </p>
        </div>
      </section>

      <section className="min-w-0 space-y-3">
        <h2 className="text-section-title text-text-primary">Status och allvarlighetsgrad</h2>
        <div className="flex min-w-0 flex-wrap gap-2">
          <StatusBadge variant="healthy" />
          <StatusBadge variant="warning" />
          <StatusBadge variant="failed" />
          <StatusBadge variant="critical" />
          <StatusBadge variant="paused" />
          <StatusBadge variant="unknown" />
        </div>
        <div className="flex flex-wrap gap-2">
          <SeverityBadge variant="P1" />
          <SeverityBadge variant="P2" />
          <SeverityBadge variant="P3" />
          <SeverityBadge variant="P4" />
        </div>
      </section>

      <section className="min-w-0 space-y-3">
        <h2 className="text-section-title text-text-primary">Nyckeltal</h2>
        <div className="grid min-w-0 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <MetricCard
            label="Kunder som behöver hjälp"
            value="3"
            helpText="Ärenden i operativ kö"
            trendText="+1 sedan igår"
            status={<StatusBadge variant="warning" />}
          />
          <MetricCard
            label="System i drift"
            value="12/12"
            helpText="Alla kontroller gröna"
            status={<StatusBadge variant="healthy" />}
          />
          <MetricCard label="Laddar exempel" value="—" loading />
        </div>
      </section>

      <section className="min-w-0 space-y-3">
        <h2 className="text-section-title text-text-primary">Hälsostatus</h2>
        <div className="grid min-w-0 gap-3">
          <HealthIndicator
            name="Gmail-integration"
            status="warning"
            lastChecked="08:42"
            explanation="Gmail har inte hämtat nya mejl sedan 08:42"
          />
          <HealthIndicator
            name="Databas"
            status="healthy"
            lastChecked="09:01"
            explanation="Senaste backup lyckades"
          />
        </div>
      </section>

      <section className="min-w-0 space-y-3">
        <h2 className="text-section-title text-text-primary">Operativ kö (Behöver hjälp)</h2>
        <div className="hidden min-w-0 overflow-x-auto rounded-lg border border-border md:block">
          <table className="w-full min-w-0 text-table">
            <thead className="bg-surface-subtle text-left text-label text-text-secondary">
              <tr>
                <th className="p-3">Tenant</th>
                <th className="p-3">Problem</th>
                <th className="p-3">Tid</th>
                <th className="p-3">Påverkan</th>
                <th className="p-3">Allvarlighetsgrad</th>
                <th className="p-3">Nästa åtgärd</th>
              </tr>
            </thead>
            <tbody>
              {DEMO_QUEUE.map((item) => (
                <tr key={item.tenant} className="border-t border-border">
                  <td className="break-all p-3 font-mono text-body-small">{item.tenant}</td>
                  <td className="p-3 text-body">{item.problem}</td>
                  <td className="p-3 text-body-small">{item.time}</td>
                  <td className="p-3 text-body-small">{item.impact}</td>
                  <td className="p-3">
                    <SeverityBadge variant={item.severity} />
                  </td>
                  <td className="p-3 text-body-small">{item.action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="space-y-3 md:hidden">
          {DEMO_QUEUE.map((item) => (
            <article
              key={item.tenant}
              className="rounded-lg border border-border bg-surface p-4 shadow-sm"
            >
              <div className="mb-2 flex items-start justify-between gap-2">
                <p className="break-all font-mono text-body-small text-text-primary">
                  {item.tenant}
                </p>
                <SeverityBadge variant={item.severity} />
              </div>
              <p className="text-body text-text-primary">{item.problem}</p>
              <p className="mt-2 text-body-small text-text-secondary">{item.impact}</p>
              <p className="mt-1 text-caption text-text-muted">
                {item.time} — {item.action}
              </p>
            </article>
          ))}
        </div>
      </section>

      <section className="min-w-0 space-y-3">
        <h2 className="text-section-title text-text-primary">Resurslista</h2>
        <div className="space-y-2">
          {DEMO_RESOURCES.map((resource) => (
            <div
              key={resource.name}
              className="flex min-w-0 flex-col gap-2 rounded-lg border border-border bg-surface p-4 sm:flex-row sm:items-center sm:justify-between"
            >
              <div>
                <p className="text-card-title text-text-primary">{resource.name}</p>
                <p className="text-body-small text-text-secondary">{resource.detail}</p>
              </div>
              <StatusBadge variant={resource.status} />
            </div>
          ))}
        </div>
      </section>

      <section className="min-w-0 space-y-3">
        <h2 className="text-section-title text-text-primary">Tillstånd</h2>
        <EmptyState
          title="Ingen åtgärd behövs"
          description="Alla kontroller är gröna just nu. Detta är ett exempel på tomt tillstånd."
        />
        <ErrorState
          title="Kunde inte hämta ködata"
          description="Anslutningen till backend misslyckades under designreferensen."
          impact="Operatören ser inte aktuella ärenden."
          recommendedAction="Försök igen eller kontrollera systemstatus."
          technicalDetails="design-reference/demo-error: connection refused (exempel)"
        />
        <LoadingState label="Laddar designreferens" rows={2} />
      </section>

      <section className="min-w-0 space-y-3">
        <h2 className="text-section-title text-text-primary">Långa texter och ID:n</h2>
        <p className="break-words text-body text-text-secondary">
          Detta är en lång svensk operatörstext som ska radbrytas korrekt utan att skapa
          oavsiktlig horisontell scroll i viewporten, även när användaren zoomar till 200
          procent och läser detaljerad information om vad som behöver göras härnäst.
        </p>
        <p
          className="break-all font-mono text-body-small text-text-muted"
          title="TENANT_1001-VERY-LONG-IDENTIFIER-FOR-DESIGN-REFERENCE-TESTING-2026-07-17"
        >
          TENANT_1001-VERY-LONG-IDENTIFIER-FOR-DESIGN-REFERENCE-TESTING-2026-07-17
        </p>
      </section>

      <section className="flex min-w-0 flex-wrap gap-3">
        <Button type="button" onClick={() => setActionOpen(true)}>
          Öppna normal dialog
        </Button>
        <Button type="button" variant="outline" onClick={() => setCriticalOpen(true)}>
          Öppna kritisk dialog
        </Button>
      </section>

      <ActionDialog
        open={actionOpen}
        title="Bekräfta exempelåtgärd"
        consequence="Detta är en designreferens. Ingen riktig write utförs."
        primaryLabel="Fortsätt"
        onConfirm={() => setActionOpen(false)}
        onClose={() => setActionOpen(false)}
      />

      <CriticalActionDialog
        open={criticalOpen}
        title="Kritisk exempelåtgärd"
        consequence="Detta är en designreferens för kritiska writes. Ingen backend-action körs."
        primaryLabel="Utför kritisk åtgärd"
        onConfirm={() => setCriticalOpen(false)}
        onClose={() => setCriticalOpen(false)}
      />
    </div>
  )
}
