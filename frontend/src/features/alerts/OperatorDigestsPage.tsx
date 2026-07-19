import { Link } from "react-router-dom"

import { ErrorState } from "@/components/operator/ErrorState"
import { LoadingState } from "@/components/operator/LoadingState"
import { PageHeader } from "@/components/operator/PageHeader"
import { SeverityBadge } from "@/components/operator/SeverityBadge"

import { alertSeverityBadge, alertSeverityLabel, formatTimestamp } from "./formatters"
import { useOperatorDigestsQuery } from "./queries"

export function OperatorDigestsPage() {
  const { data, isLoading, isError, error } = useOperatorDigestsQuery()

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <PageHeader
        title="Operatörssammanfattningar"
        description="Dagliga sammanfattningar baserade på öppna och nyligen lösta larm."
        actions={
          <Link
            to="/alerts"
            className="inline-flex max-w-full shrink-0 rounded-md border border-border bg-surface px-3 py-2 text-body text-text-primary"
          >
            Till larm
          </Link>
        }
      />

      {isLoading ? (
        <LoadingState label="Laddar sammanfattningar…" rows={4} />
      ) : isError ? (
        <ErrorState
          title="Kunde inte ladda sammanfattningar"
          description="Sammanfattningarna kunde inte hämtas just nu."
          recommendedAction="Försök uppdatera sidan."
          technicalDetails={error instanceof Error ? error.message : undefined}
        />
      ) : data?.items.length ? (
        <ul className="space-y-3">
          {data.items.map((digest) => (
            <li
              key={digest.id}
              className="rounded-lg border border-border bg-surface p-4"
            >
              <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <p className="break-words font-medium text-text-primary">
                    {digest.digest_date}
                  </p>
                  <p className="text-body-small text-text-muted">
                    {digest.items.length} poster · {digest.delivery_status}
                  </p>
                </div>
                <p className="text-body-small text-text-secondary">
                  {formatTimestamp(digest.generated_at)}
                </p>
              </div>
              {digest.items.slice(0, 3).map((item) => (
                <div
                  key={`${digest.id}-${item.priority}`}
                  className="mt-3 flex min-w-0 items-start gap-2 border-t border-border pt-3"
                >
                  {item.severity ? (
                    <SeverityBadge variant={alertSeverityBadge(item.severity)} />
                  ) : null}
                  <div className="min-w-0">
                    <p className="break-words text-body text-text-primary">{item.title}</p>
                    <p className="break-words text-body-small text-text-muted">
                      {item.summary}
                    </p>
                    {item.severity ? (
                      <p className="text-caption text-text-muted">
                        {alertSeverityLabel(item.severity)}
                      </p>
                    ) : null}
                  </div>
                </div>
              ))}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-body text-text-muted">
          Inga sammanfattningar har genererats ännu.
        </p>
      )}
    </div>
  )
}
