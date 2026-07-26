import { useQuery } from "@tanstack/react-query"
import { Link, useLocation, useParams } from "react-router-dom"

import { ErrorState } from "@/components/shared/ErrorState"
import { LoadingState } from "@/components/shared/LoadingState"
import { useCustomerAuth } from "@/customer/auth/CustomerAuthProvider"
import { CustomerPageContainer } from "@/customer/components/CustomerPageContainer"
import { CustomerPageHeader } from "@/customer/components/CustomerPageHeader"
import { WorkDetailTimeline } from "@/customer/features/work-detail/WorkDetailTimeline"
import {
  displayStatusLabel,
  formatOverviewDateTime,
  workQueueTypeLabel,
} from "@/customer/features/work-queues/workQueueFormatters"
import {
  resolveWorkItemBackPath,
  type WorkItemReturnState,
} from "@/customer/navigation/workItemNavigation"
import { cn } from "@/lib/utils"

export function buildWorkItemQueryKey(workItemId: string) {
  return ["customer-workspace", "work-item", workItemId] as const
}

function statusTone(
  status: string,
): string {
  switch (status) {
    case "prioritized":
    case "waiting_for_decision":
      return "border-status-warning/30 bg-status-warning/5"
    case "needs_help":
    case "failed":
      return "border-status-danger/30 bg-status-danger/5"
    case "completed":
      return "border-status-success/30 bg-status-success/5"
    case "unknown":
      return "border-border bg-surface-subtle"
    default:
      return "border-border bg-surface"
  }
}

export function WorkDetailPage() {
  const { workItemId = "" } = useParams()
  const location = useLocation()
  const { dataSource } = useCustomerAuth()
  const returnState = location.state as WorkItemReturnState | null

  const {
    data,
    isLoading,
    isError,
    refetch,
    isFetched,
  } = useQuery({
    queryKey: buildWorkItemQueryKey(workItemId),
    queryFn: () => dataSource.getWorkItem(workItemId),
    enabled: Boolean(workItemId),
    retry: (failureCount, error) => {
      if (error instanceof Error && error.message === "NOT_FOUND") return false
      return failureCount < 1
    },
    refetchOnWindowFocus: false,
  })

  if (isLoading) {
    return (
      <CustomerPageContainer>
        <CustomerPageHeader
          title="Arbetsobjekt"
          description="Laddar detaljer…"
        />
        <LoadingState label="Laddar arbetsobjekt…" rows={4} />
      </CustomerPageContainer>
    )
  }

  if (isError) {
    return (
      <CustomerPageContainer>
        <CustomerPageHeader title="Arbetsobjekt" />
        <ErrorState
          title="Arbetsobjektet kunde inte laddas"
          description="Försök igen om en stund."
        />
        <button
          type="button"
          className="mt-4 inline-flex min-h-11 items-center rounded-md border border-border bg-surface px-4 text-body font-medium text-text-primary hover:bg-surface-subtle"
          onClick={() => void refetch()}
        >
          Försök igen
        </button>
      </CustomerPageContainer>
    )
  }

  if (isFetched && !data) {
    const backPath = resolveWorkItemBackPath(returnState, "unknown")
    return (
      <CustomerPageContainer>
        <CustomerPageHeader
          title="Arbetsobjektet hittades inte"
          description="Det du söker finns inte i förhandsvisningen eller är inte tillgängligt."
        />
        <Link
          to={backPath}
          className="inline-flex min-h-11 items-center rounded-md border border-border bg-surface px-4 text-body font-medium text-text-primary hover:bg-surface-subtle"
        >
          Tillbaka
        </Link>
      </CustomerPageContainer>
    )
  }

  if (!data) return null

  const statusLabel = displayStatusLabel(data.customer_status_label)
  const backPath = resolveWorkItemBackPath(returnState, data.type)

  return (
    <CustomerPageContainer>
      <p className="mb-4">
        <Link
          to={backPath}
          className="inline-flex min-h-11 items-center text-body font-medium text-brand underline-offset-2 hover:underline"
        >
          ← Tillbaka
        </Link>
      </p>

      <CustomerPageHeader
        title={data.title}
        description={`${workQueueTypeLabel(data.type)} · ${statusLabel}`}
      />

      <div
        className={cn(
          "mb-6 rounded-lg border p-4",
          statusTone(data.customer_status),
        )}
      >
        <dl className="grid gap-2 text-body-small text-text-secondary">
          {data.customer_name ? (
            <div className="flex flex-wrap gap-1">
              <dt className="font-medium text-text-primary">Kund:</dt>
              <dd className="break-words">{data.customer_name}</dd>
            </div>
          ) : null}
          {data.customer_email ? (
            <div className="flex flex-wrap gap-1">
              <dt className="font-medium text-text-primary">E-post:</dt>
              <dd className="break-all">{data.customer_email}</dd>
            </div>
          ) : null}
          {data.priority_label ? (
            <div className="flex flex-wrap gap-1">
              <dt className="font-medium text-text-primary">Prioritet:</dt>
              <dd>{data.priority_label}</dd>
            </div>
          ) : null}
          <div className="flex flex-wrap gap-1">
            <dt className="font-medium text-text-primary">Skapad:</dt>
            <dd>{formatOverviewDateTime(data.created_at)}</dd>
          </div>
          <div className="flex flex-wrap gap-1">
            <dt className="font-medium text-text-primary">Uppdaterad:</dt>
            <dd>{formatOverviewDateTime(data.updated_at)}</dd>
          </div>
        </dl>
      </div>

      <section className="mb-6" aria-labelledby="work-summary-heading">
        <h2 id="work-summary-heading" className="text-section-title text-text-primary">
          Sammanfattning
        </h2>
        <p className="mt-2 break-words text-body text-text-secondary">
          {data.summary}
        </p>
      </section>

      <section className="mb-6" aria-labelledby="work-status-heading">
        <h2 id="work-status-heading" className="text-section-title text-text-primary">
          Nuvarande läge
        </h2>
        <div className="mt-2 space-y-2 rounded-lg border border-border bg-surface p-4 text-body text-text-secondary">
          {data.human_takeover_required ? (
            <p>
              Systemet behöver hjälp för att fortsätta. En medarbetare behöver
              granska ärendet.
            </p>
          ) : null}
          {data.waiting_for ? (
            <p>
              <span className="font-medium text-text-primary">Väntar på:</span>{" "}
              {data.waiting_for}
            </p>
          ) : (
            <p>Inget särskilt väntar just nu utöver normal uppföljning.</p>
          )}
        </div>
      </section>

      <section aria-labelledby="work-timeline-heading">
        <h2 id="work-timeline-heading" className="text-section-title text-text-primary">
          Historik
        </h2>
        <div className="mt-3">
          <WorkDetailTimeline items={data.timeline} />
        </div>
      </section>
    </CustomerPageContainer>
  )
}
