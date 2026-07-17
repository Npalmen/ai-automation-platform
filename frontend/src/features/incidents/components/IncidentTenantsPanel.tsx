import { Link } from "react-router-dom"

import type { IncidentTenantOut } from "../types"

type IncidentTenantsPanelProps = {
  tenants: IncidentTenantOut[]
}

export function IncidentTenantsPanel({ tenants }: IncidentTenantsPanelProps) {
  if (tenants.length === 0) {
    return <p className="text-body text-text-muted">Inga kopplade kunder.</p>
  }

  return (
    <ul className="flex min-w-0 flex-col gap-2">
      {tenants.map((tenant) => (
        <li key={tenant.tenant_id}>
          <Link
            to={`/customers/${encodeURIComponent(tenant.tenant_id)}`}
            className="text-body text-text-primary underline"
          >
            {tenant.tenant_name_snapshot ?? tenant.tenant_id}
          </Link>
        </li>
      ))}
    </ul>
  )
}
