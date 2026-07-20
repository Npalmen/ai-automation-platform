import { Link } from "react-router-dom"

const SAFE_STEP_PATTERN = /^[a-z_]+$/

/** Map server readiness action_link to an in-app onboarding route. */
export function resolveReadinessActionLink(
  template: string | null | undefined,
  tenantId: string,
): string | null {
  if (!template || !tenantId) return null
  const substituted = template.replace("{tenant_id}", tenantId)
  const match = substituted.match(/^\/ops\/customers\/([^/?#]+)\/onboarding\?step=([a-z_]+)$/)
  if (!match) return null
  const [, routeTenantId, step] = match
  if (routeTenantId !== tenantId || !SAFE_STEP_PATTERN.test(step)) return null
  return `/customers/${encodeURIComponent(tenantId)}/onboarding?step=${encodeURIComponent(step)}`
}

type ReadinessActionLinkProps = {
  template: string | null | undefined
  tenantId: string
  stepLabel?: string | null
}

export function ReadinessActionLink({ template, tenantId, stepLabel }: ReadinessActionLinkProps) {
  const to = resolveReadinessActionLink(template, tenantId)
  if (!to) return null
  const label = stepLabel ? `Gå till ${stepLabel}` : "Gå till steg"
  return (
    <Link
      to={to}
      className="inline-flex min-h-11 items-center text-body-small text-text-primary underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
    >
      {label}
    </Link>
  )
}
