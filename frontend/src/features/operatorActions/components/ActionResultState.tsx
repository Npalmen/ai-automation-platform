import type { OperatorActionResponse, OperatorActionStatus } from "../types"

type ActionResultStateProps = {
  status: OperatorActionStatus | "error"
  message: string
}

const SUCCESS_STATUSES = new Set<OperatorActionStatus>(["completed", "no_change"])

export function ActionResultState({ status, message }: ActionResultStateProps) {
  const isSuccess = status !== "error" && SUCCESS_STATUSES.has(status)
  const tone = isSuccess ? "text-status-success" : "text-status-danger"

  return (
    <div className={`rounded-md border border-border bg-page p-3 ${tone}`} role="status">
      <p className="text-label font-medium">
        {isSuccess ? "Åtgärden slutförd" : "Åtgärden kunde inte slutföras"}
      </p>
      <p className="mt-1 break-words text-body-small">{message}</p>
    </div>
  )
}

export function responseIsSuccess(response: OperatorActionResponse): boolean {
  return response.status === "completed" || response.status === "no_change"
}
