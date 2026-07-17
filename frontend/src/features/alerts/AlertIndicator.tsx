import { Link } from "react-router-dom"

import { Badge } from "@/components/ui/badge"
import { useAlertSummaryQuery } from "@/features/alerts/queries"

export function AlertIndicator() {
  const { data } = useAlertSummaryQuery()
  const urgentCount = (data?.open_critical ?? 0) + (data?.open_high ?? 0)

  return (
    <Link
      to="/alerts"
      className="inline-flex min-h-11 items-center gap-2 rounded-md border border-border bg-surface px-3 text-body text-text-primary hover:bg-surface-subtle"
      aria-label={
        urgentCount > 0
          ? `${urgentCount} kritiska eller höga larm`
          : "Inga kritiska larm"
      }
    >
      <span aria-hidden="true">🔔</span>
      <span className="hidden sm:inline">Larm</span>
      {urgentCount > 0 ? (
        <Badge variant="outline" className="border-status-danger text-status-danger">
          {urgentCount}
        </Badge>
      ) : null}
    </Link>
  )
}
