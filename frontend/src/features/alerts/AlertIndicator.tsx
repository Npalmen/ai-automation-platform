import { Link } from "react-router-dom"

import { Badge } from "@/components/ui/badge"
import { useAlertSummaryQuery } from "@/features/alerts/queries"

export function AlertIndicator() {
  const { data } = useAlertSummaryQuery()
  const urgentCount = (data?.open_critical ?? 0) + (data?.open_high ?? 0)
  const warningCount = data?.open_warning ?? 0
  const totalOpen = data?.total_open ?? 0

  return (
    <Link
      to="/alerts"
      className="inline-flex min-h-11 min-w-0 max-w-full items-center gap-2 rounded-md border border-border bg-surface px-2 text-body text-text-primary hover:bg-surface-subtle md:px-3"
      aria-label={
        urgentCount > 0
          ? `${urgentCount} kritiska eller höga larm`
          : warningCount > 0
            ? `${warningCount} varningslarm`
            : "Inga aktiva larm"
      }
      title={
        totalOpen > 0
          ? `${totalOpen} öppna larm (kritiska: ${data?.open_critical ?? 0}, höga: ${data?.open_high ?? 0})`
          : "Inga öppna larm"
      }
    >
      <span aria-hidden="true">🔔</span>
      <span className="hidden md:inline">Larm</span>
      {urgentCount > 0 ? (
        <Badge variant="outline" className="border-status-danger text-status-danger">
          {urgentCount}
        </Badge>
      ) : warningCount > 0 ? (
        <Badge variant="outline" className="border-status-warning text-status-warning">
          {warningCount}
        </Badge>
      ) : null}
    </Link>
  )
}
