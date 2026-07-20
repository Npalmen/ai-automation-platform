import type { ReactNode } from "react"
import { Link, useParams } from "react-router-dom"

import { AuditTimeline } from "@/components/operator/AuditTimeline"
import { ErrorState } from "@/components/operator/ErrorState"
import { HealthIndicator } from "@/components/operator/HealthIndicator"
import { LoadingState } from "@/components/operator/LoadingState"
import { MetricCard } from "@/components/operator/MetricCard"
import { PageHeader } from "@/components/operator/PageHeader"
import { StatusBadge } from "@/components/operator/StatusBadge"
import { TenantIdentifier } from "@/components/operator/TenantIdentifier"
import { PriorityList } from "@/features/overview/components/PriorityList"
import { OperatorActionsSection,
} from "@/features/operatorActions/components/OperatorActionsSection"
import { CustomerLifecyclePanel } from "@/features/customers/CustomerLifecyclePanel"
import { GmailIntegrationPanel } from "@/features/customers/GmailIntegrationPanel"
import { ApiError } from "@/api/client"

import { formatActivityAt, integrationSummaryLabel, tenantStatusLabel } from "./formatters"
import { useTenantDetailQuery } from "./queries"
import type { TenantIntegrationStatus } from "./types"

function Section({
  title,
  children,
}: {
  title: string
  children: ReactNode
}) {
  return (
    <section className="min-w-0 rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-section-title text-text-primary">{title}</h2>
      {children}
    </section>
  )
}

function integrationExplanation(item: TenantIntegrationStatus): string {
  const source =
    item.data_source === "integration_health_check"
      ? "Integrationshälsokontroll"
      : "OAuth + händelselogg"
  const action = item.recommended_action ? ` ${item.recommended_action}` : ""
  return `${source}. ${item.description}${action}`
}

export function CustomerDetailPage() {
  const { tenantId } = useParams<{ tenantId: string }>()
  const { data, isLoading, isError, error } = useTenantDetailQuery(tenantId)

  if (isLoading) {
    return (
      <div className="flex min-w-0 flex-col gap-6">
        <PageHeader title="Kunddetalj" description="Laddar kundinformation…" />
        <LoadingState label="Laddar kunddetalj…" rows={8} />
      </div>
    )
  }

  if (isError || !data) {
    const is404 = error instanceof ApiError && error.status === 404
    return (
      <div className="flex min-w-0 flex-col gap-6">
        <PageHeader title="Kunddetalj" />
        <ErrorState
          title={is404 ? "Kunden hittades inte" : "Kunde inte ladda kunddetalj"}
          description={
            is404
              ? "Det finns ingen tenant med det angivna ID:t."
              : "Kunddetaljen kunde inte hämtas just nu."
          }
          recommendedAction={is404 ? "Gå tillbaka till kundlistan." : "Försök uppdatera sidan."}
          technicalDetails={error instanceof Error ? error.message : undefined}
        />
        <Link
          to="/customers"
          className="self-start text-body text-text-primary underline"
        >
          Tillbaka till kunder
        </Link>
      </div>
    )
  }

  const { tenant, health, integrations, jobs, approvals, manual_review, recent_errors, usage, audit, onboarding_config, lifecycle, available_actions } =
    data

  const healthCheckIntegrations = [
    ["gmail", integrations.gmail],
    ["monday", integrations.monday],
    ["fortnox", integrations.fortnox],
  ] as const

  const eventIntegrations = [
    ["visma", integrations.visma],
    ["google_sheets", integrations.google_sheets],
  ] as const

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <PageHeader
        title={tenant.name}
        description={health.summary}
        status={<StatusBadge variant={health.level} label={health.label} />}
        actions={
          <div className="flex flex-wrap gap-2">
            <Link
              to={`/customers/${tenant.tenant_id}/onboarding`}
              className="rounded-md border border-border bg-surface px-3 py-2 text-label text-text-primary hover:bg-surface-subtle"
            >
              Fortsätt onboarding
            </Link>
            <Link
              to={`/customers/${tenant.tenant_id}/onboarding?step=readiness`}
              className="rounded-md border border-border bg-surface px-3 py-2 text-label text-text-primary hover:bg-surface-subtle"
            >
              Readiness
            </Link>
            <Link
              to="/customers"
              className="rounded-md border border-border bg-surface px-3 py-2 text-label text-text-primary hover:bg-surface-subtle"
            >
              Tillbaka
            </Link>
          </div>
        }
      />

      <div className="flex min-w-0 flex-wrap items-center gap-3">
        <TenantIdentifier tenantId={tenant.tenant_id} />
        <span className="text-body-small text-text-secondary">
          Kontostatus: {tenantStatusLabel(tenant.tenant_status)}
        </span>
      </div>

      <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-6">
          <Section title="Grunduppgifter">
            <dl className="grid gap-3 sm:grid-cols-2">
              <div>
                <dt className="text-caption text-text-secondary">Paket</dt>
                <dd className="text-body text-text-primary">—</dd>
              </div>
              <div>
                <dt className="text-caption text-text-secondary">Operatörsansvarig</dt>
                <dd className="text-body text-text-primary">Okänd</dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-caption text-text-secondary">Aktiverade moduler</dt>
                <dd className="text-body text-text-primary">
                  {tenant.enabled_modules.length > 0
                    ? tenant.enabled_modules.join(", ")
                    : "Inga"}
                </dd>
              </div>
            </dl>
          </Section>

          <Section title="Onboarding-konfiguration (read-only)">
            <dl className="grid gap-3 sm:grid-cols-2">
              <div>
                <dt className="text-caption text-text-secondary">Settings schema</dt>
                <dd className="text-body text-text-primary">
                  {onboarding_config.schema_version ?? "—"}
                </dd>
              </div>
              <div>
                <dt className="text-caption text-text-secondary">Intake-läge</dt>
                <dd className="text-body text-text-primary">
                  {onboarding_config.intake.mode ?? "—"}
                </dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-caption text-text-secondary">Serviceprofiler</dt>
                <dd className="text-body text-text-primary">
                  {onboarding_config.service_profiles.length > 0
                    ? onboarding_config.service_profiles.join(", ")
                    : "Inga"}
                </dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-caption text-text-secondary">Intern routing</dt>
                <dd className="text-body text-text-primary">
                  {Object.keys(onboarding_config.internal_routing_hints).length > 0
                    ? Object.entries(onboarding_config.internal_routing_hints)
                        .map(([k, v]) => `${k} → ${v}`)
                        .join("; ")
                    : "Inga overrides"}
                </dd>
              </div>
              {onboarding_config.intake.activation_cutoff_at ? (
                <div className="sm:col-span-2">
                  <dt className="text-caption text-text-secondary">Aktiverings-cutoff</dt>
                  <dd className="text-body text-text-primary">
                    {onboarding_config.intake.activation_cutoff_at}
                    {onboarding_config.intake.enforcement
                      ? ` (${onboarding_config.intake.enforcement})`
                      : ""}
                  </dd>
                </div>
              ) : null}
            </dl>
          </Section>

          <Section title="Driftsstatus">
            <p className="text-body text-text-primary">{health.summary}</p>
          </Section>

          <OperatorActionsSection
            tenantId={tenant.tenant_id}
            tenantLabel={tenant.name}
            actions={available_actions ?? []}
          />

          <Section title="Integrationer (hälsokontroll)">
            <GmailIntegrationPanel tenantId={tenant.tenant_id} />
            <div className="mt-3 flex flex-col gap-3">
              {healthCheckIntegrations.map(([key, item]) => (
                <HealthIndicator
                  key={key}
                  name={integrationSummaryLabel(key)}
                  status={item.status}
                  lastChecked={formatActivityAt(item.last_success_at ?? item.last_error_at)}
                  explanation={integrationExplanation(item)}
                />
              ))}
            </div>
          </Section>

          <Section title="Integrationer (OAuth / händelselogg)">
            <div className="flex flex-col gap-3">
              {eventIntegrations.map(([key, item]) => (
                <HealthIndicator
                  key={key}
                  name={integrationSummaryLabel(key)}
                  status={item.status}
                  lastChecked={formatActivityAt(item.last_success_at ?? item.last_error_at)}
                  explanation={integrationExplanation(item)}
                />
              ))}
            </div>
          </Section>

          <Section title="Senaste jobb">
            <p className="mb-3 text-body-small text-text-secondary">
              Totalt {jobs.total} jobb · {jobs.jobs_last_30d} senaste 30 dagarna
            </p>
            {jobs.recent.length === 0 ? (
              <p className="text-body text-text-secondary">Inga jobb att visa.</p>
            ) : (
              <ul className="space-y-2">
                {jobs.recent.map((job) => (
                  <li
                    key={job.job_id}
                    className="rounded-md border border-border bg-page px-3 py-2 text-body-small"
                  >
                    <span className="font-medium text-text-primary">{job.job_type}</span>
                    {" · "}
                    {job.status}
                    {" · "}
                    {formatActivityAt(job.updated_at)}
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="Väntande godkännanden">
            <p className="mb-3 text-body-small text-text-secondary">
              {approvals.pending_count} väntande totalt
            </p>
            {approvals.recent.length === 0 ? (
              <p className="text-body text-text-secondary">Inga väntande godkännanden.</p>
            ) : (
              <ul className="space-y-2">
                {approvals.recent.map((item) => (
                  <li
                    key={item.approval_id}
                    className="rounded-md border border-border bg-page px-3 py-2 text-body-small"
                  >
                    <Link
                      to={`/needs-help/approval:${encodeURIComponent(item.approval_id)}`}
                      className="font-medium text-text-primary underline"
                    >
                      {item.title ?? item.job_type}
                    </Link>
                    {" · "}
                    {formatActivityAt(item.created_at)}
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="Manuell granskning">
            <p className="mb-3 text-body-small text-text-secondary">
              {manual_review.total} öppna totalt
            </p>
            {manual_review.recent.length === 0 ? (
              <p className="text-body text-text-secondary">Inga öppna manuella granskningar.</p>
            ) : (
              <ul className="space-y-2">
                {manual_review.recent.map((item) => (
                  <li
                    key={item.job_id}
                    className="rounded-md border border-border bg-page px-3 py-2 text-body-small"
                  >
                    {item.subject ?? item.job_type} · {item.manual_review_reason ?? "Ingen anledning"}
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="Senaste fel">
            <PriorityList items={recent_errors} />
          </Section>
        </div>

        <div className="flex min-w-0 flex-col gap-6">
          <CustomerLifecyclePanel tenantId={tenant.tenant_id} initialLifecycle={lifecycle ?? null} />

          <Section title="Användning (30 d)">
            <div className="grid gap-3 sm:grid-cols-2">
              <MetricCard label="Jobb skapade" value={usage.jobs_created} />
              <MetricCard label="Jobb slutförda" value={usage.jobs_completed} />
              <MetricCard label="Väntande godkännanden" value={usage.pending_approvals} />
              <MetricCard label="Blockerade flöden" value={usage.blocked_flows} />
              <MetricCard label="Automationsgrad" value={`${usage.automation_rate_percent}%`} />
              <MetricCard
                label="Sparad tid"
                value={`${usage.time_saved_hours} h`}
                helpText="Uppskattning från lyckade dispatches."
              />
            </div>
          </Section>

          <Section title="Granskning (audit)">
            <AuditTimeline
              events={audit.recent.map((event) => ({
                event_id: event.event_id,
                category: event.category,
                action: event.action,
                status: event.status,
                created_at: event.created_at,
              }))}
              total={audit.total}
            />
          </Section>
        </div>
      </div>
    </div>
  )
}
