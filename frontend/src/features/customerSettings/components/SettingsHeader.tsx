import { PageHeader } from "@/components/operator/PageHeader"
import { StatusBadge } from "@/components/operator/StatusBadge"
import { TenantIdentifier } from "@/components/operator/TenantIdentifier"

import {
  formatTimestamp,
  lifecycleStatusLabel,
  readinessStatusLabel,
  tenantStatusLabel,
} from "../formatters"
import type { CustomerSettingsAggregate } from "../types"

type Props = {
  data: CustomerSettingsAggregate
  roleLabel: string
}

function readinessVariant(status: string): "healthy" | "warning" | "critical" | "unknown" {
  if (status === "ready") return "healthy"
  if (status === "ready_with_warnings") return "warning"
  if (status === "not_ready") return "critical"
  return "unknown"
}

export function SettingsHeader({ data, roleLabel }: Props) {
  const readiness = data.effective_readiness
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader
        title={`Inställningar — ${data.domains.identity?.name ?? data.tenant_id}`}
        description="Redigera aktiv kundkonfiguration. Ändringar sparas per domän med versionskontroll."
        status={
          <StatusBadge
            variant={readinessVariant(readiness.overall_status)}
            label={readinessStatusLabel(readiness.overall_status)}
          />
        }
      />
      <div className="grid min-w-0 gap-3 rounded-lg border border-border bg-surface p-4 sm:grid-cols-2 xl:grid-cols-4">
        <div>
          <p className="text-caption text-text-secondary">Tenant</p>
          <TenantIdentifier tenantId={data.tenant_id} />
        </div>
        <div>
          <p className="text-caption text-text-secondary">Status</p>
          <p className="text-body text-text-primary">
            {tenantStatusLabel(data.tenant_status)} · {lifecycleStatusLabel(data.lifecycle_status)}
          </p>
        </div>
        <div>
          <p className="text-caption text-text-secondary">Config-version</p>
          <p className="text-body text-text-primary">{data.config_version}</p>
        </div>
        <div>
          <p className="text-caption text-text-secondary">Senast uppdaterad</p>
          <p className="text-body text-text-primary">
            {formatTimestamp(data.last_updated.at)}
            {data.last_updated.by ? ` av ${data.last_updated.by}` : ""}
          </p>
        </div>
        <div>
          <p className="text-caption text-text-secondary">Behörighet</p>
          <p className="text-body text-text-primary">{roleLabel}</p>
        </div>
        <div>
          <p className="text-caption text-text-secondary">Readiness</p>
          <p className="text-body text-text-primary">
            {readinessStatusLabel(readiness.overall_status)}
            {readiness.is_stale ? " · inaktuell" : ""}
          </p>
        </div>
      </div>
    </div>
  )
}
