import { WorkspaceModeBadge } from "@/customer/components/WorkspaceModeBadge"
import { formatOverviewDateTime } from "@/customer/features/overview/overviewFormatters"

type OverviewHeaderProps = {
  companyName: string
  lastUpdatedAt: string | null
  isRefreshing?: boolean
}

export function OverviewHeader({
  companyName,
  lastUpdatedAt,
  isRefreshing = false,
}: OverviewHeaderProps) {
  return (
    <header className="mb-8 min-w-0">
      <div className="flex flex-wrap items-center gap-3">
        <h1
          className="text-page-title text-text-primary"
          tabIndex={-1}
        >
          Översikt
        </h1>
        <WorkspaceModeBadge />
        {isRefreshing ? (
          <span className="text-body-small text-text-muted" aria-live="polite">
            Uppdaterar…
          </span>
        ) : null}
      </div>
      <p className="mt-2 max-w-3xl text-body text-text-secondary">
        Din dagliga överblick över vad den digitala medarbetaren har hanterat och
        vad som behöver din uppmärksamhet.
      </p>
      <p className="mt-3 text-body-small text-text-muted">
        <span className="font-medium text-text-secondary">{companyName}</span>
        {lastUpdatedAt ? (
          <>
            {" "}
            · Senast uppdaterad {formatOverviewDateTime(lastUpdatedAt)}
          </>
        ) : null}
        {" "}
        · Förhandsvisning med exempeldata, inte liveuppdatering
      </p>
    </header>
  )
}
