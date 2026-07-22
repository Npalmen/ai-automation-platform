import { StatusBadge } from "@/components/operator/StatusBadge"

import { SETTINGS_TABS } from "../constants"
import { readinessStatusLabel } from "../formatters"
import type { EffectiveReadiness } from "../types"
import { resolveActionDomainTab } from "../utils"

function tabLabelForActionDomain(actionDomain: string): string {
  const tab = resolveActionDomainTab(actionDomain)
  return SETTINGS_TABS.find((item) => item.id === tab)?.label ?? actionDomain
}

type Props = {
  readiness: EffectiveReadiness
  onOpenTab: (actionDomain: string) => void
}

function statusVariant(status: string): "healthy" | "warning" | "critical" | "unknown" {
  if (status === "ready") return "healthy"
  if (status === "ready_with_warnings") return "warning"
  if (status === "not_ready") return "critical"
  return "unknown"
}

export function ReadinessSummaryPanel({ readiness, onOpenTab }: Props) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge
          variant={statusVariant(readiness.overall_status)}
          label={readinessStatusLabel(readiness.overall_status)}
        />
        {readiness.is_stale ? <StatusBadge variant="warning" label="Inaktuell readiness" /> : null}
      </div>

      {readiness.is_stale && readiness.stale_domains.length > 0 ? (
        <section className="rounded-md border border-border bg-page p-3">
          <h3 className="text-body font-medium text-text-primary">Inaktuella domäner</h3>
          <p className="mt-1 text-body-small text-text-secondary">
            {readiness.stale_domains.join(", ")}
          </p>
        </section>
      ) : null}

      {readiness.blockers.length > 0 ? (
        <section className="rounded-md border border-border bg-page p-3">
          <h3 className="text-body font-medium text-text-primary">Blockerare</h3>
          <ul className="mt-2 space-y-2">
            {readiness.blockers.map((blocker) => (
              <li key={blocker.code} className="rounded-md border border-border bg-surface px-3 py-2">
                <p className="text-body-small text-text-primary">{blocker.message}</p>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <StatusBadge variant="critical" label="Blockerar" />
                  <button
                    type="button"
                    className="min-h-11 text-body-small text-text-primary underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
                    onClick={() => onOpenTab(blocker.action_domain)}
                  >
                    Gå till {tabLabelForActionDomain(blocker.action_domain)}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {readiness.warnings.length > 0 ? (
        <section className="rounded-md border border-border bg-page p-3">
          <h3 className="text-body font-medium text-text-primary">Varningar</h3>
          <ul className="mt-2 space-y-2">
            {readiness.warnings.map((warning) => (
              <li key={warning.code} className="text-body-small text-text-secondary">
                <button
                  type="button"
                  className="text-left underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
                  onClick={() => onOpenTab(warning.action_domain)}
                >
                  {warning.message}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {readiness.affected_capabilities.length > 0 ? (
        <section className="rounded-md border border-border bg-page p-3">
          <h3 className="text-body font-medium text-text-primary">Påverkade capabilities</h3>
          <p className="mt-1 text-body-small text-text-secondary">
            {readiness.affected_capabilities.join(", ")}
          </p>
        </section>
      ) : null}

      <section className="rounded-md border border-border bg-page p-3">
        <h3 className="text-body font-medium text-text-primary">Integrationsgrupper</h3>
        <ul className="mt-2 space-y-2">
          {readiness.integration_group_status.groups.map((group) => (
            <li
              key={group.group_key}
              className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-surface px-3 py-2 text-body-small"
            >
              <span className="text-text-primary">{group.group_key}</span>
              <StatusBadge
                variant={group.satisfied ? "healthy" : "warning"}
                label={group.satisfied ? "Uppfylld" : group.reason}
              />
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
