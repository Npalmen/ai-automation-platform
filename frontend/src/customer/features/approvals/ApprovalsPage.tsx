import { useQuery } from "@tanstack/react-query"
import { useCallback, useEffect, useMemo } from "react"
import { useSearchParams } from "react-router-dom"

import { EmptyState } from "@/components/shared/EmptyState"
import { ErrorState } from "@/components/shared/ErrorState"
import { LoadingState } from "@/components/shared/LoadingState"
import { useCustomerAuth } from "@/customer/auth/CustomerAuthProvider"
import { ApprovalItemCard } from "@/customer/features/approvals/ApprovalItemCard"
import { QueueResultSummary } from "@/customer/features/work-queues/QueueResultSummary"
import {
  APPROVAL_STATUS_FILTERS,
  WORK_QUEUE_PAGE_SIZE,
} from "@/customer/features/work-queues/workQueueConstants"
import { WorkQueuePageLayout } from "@/customer/features/work-queues/WorkQueuePageLayout"
import { WorkQueuePagination } from "@/customer/features/work-queues/WorkQueuePagination"
import { WorkQueuePartialError } from "@/customer/features/work-queues/WorkQueuePartialError"
import { WorkQueueToolbar } from "@/customer/features/work-queues/WorkQueueToolbar"
import {
  buildApprovalSearchParams,
  normalizePageForTotal,
  parseApprovalUrlState,
  workQueueOffset,
} from "@/customer/features/work-queues/workQueueUrlState"
import type { ApprovalListParams } from "@/customer/types/approvals"

export function buildApprovalsQueryKey(params: ApprovalListParams) {
  return ["customer-workspace", "approvals", params] as const
}

export function ApprovalsPage() {
  const { dataSource } = useCustomerAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const urlState = useMemo(
    () => parseApprovalUrlState(searchParams),
    [searchParams],
  )

  const queryParams = useMemo<ApprovalListParams>(
    () => ({
      status: urlState.status,
      limit: WORK_QUEUE_PAGE_SIZE,
      offset: workQueueOffset(urlState.page),
    }),
    [urlState],
  )

  const {
    data,
    isLoading,
    isError,
    isFetching,
    refetch,
  } = useQuery({
    queryKey: buildApprovalsQueryKey(queryParams),
    queryFn: () => dataSource.listApprovals(queryParams),
    retry: 1,
    refetchOnWindowFocus: false,
  })

  const updateUrlState = useCallback(
    (next: Partial<typeof urlState>) => {
      const merged = { ...urlState, ...next }
      setSearchParams(buildApprovalSearchParams(merged), { replace: false })
    },
    [setSearchParams, urlState],
  )

  useEffect(() => {
    if (!data) return
    const normalizedPage = normalizePageForTotal(
      urlState.page,
      data.total,
      WORK_QUEUE_PAGE_SIZE,
    )
    if (normalizedPage !== urlState.page) {
      updateUrlState({ page: normalizedPage })
    }
  }, [data, updateUrlState, urlState.page])

  if (isLoading) {
    return (
      <WorkQueuePageLayout
        title="Godkännanden"
        description="Förslag som i framtiden kan kräva beslut. I förhandsvisningen visas de read-only."
      >
        <LoadingState label="Laddar godkännanden…" rows={4} />
      </WorkQueuePageLayout>
    )
  }

  if (isError || !data) {
    return (
      <WorkQueuePageLayout
        title="Godkännanden"
        description="Förslag som i framtiden kan kräva beslut. I förhandsvisningen visas de read-only."
      >
        <ErrorState
          title="Godkännanden kunde inte laddas"
          description="Försök igen om en stund. Om problemet kvarstår kan du kontakta support."
        />
        <button
          type="button"
          className="mt-4 inline-flex min-h-11 items-center rounded-md border border-border bg-surface px-4 text-body font-medium text-text-primary hover:bg-surface-subtle"
          onClick={() => void refetch()}
        >
          Försök igen
        </button>
      </WorkQueuePageLayout>
    )
  }

  return (
    <WorkQueuePageLayout
      title="Godkännanden"
      description="Förslag som i framtiden kan kräva beslut. I förhandsvisningen visas de read-only."
      toolbar={(
        <WorkQueueToolbar>
          <div className="min-w-0">
            <label
              htmlFor="approval-status-filter"
              className="mb-1 block text-body-small font-medium text-text-primary"
            >
              Status
            </label>
            <select
              id="approval-status-filter"
              className="min-h-11 w-full min-w-[10rem] rounded-md border border-border bg-surface px-3 text-body text-text-primary"
              value={urlState.status}
              onChange={(event) =>
                updateUrlState({
                  status: event.target.value as "pending" | "all",
                  page: 1,
                })}
            >
              {APPROVAL_STATUS_FILTERS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </WorkQueueToolbar>
      )}
      summary={(
        <QueueResultSummary
          offset={data.offset}
          limit={data.limit}
          total={data.total}
          isRefreshing={isFetching && !isLoading}
        />
      )}
      partialError={<WorkQueuePartialError errors={data.partial_errors} />}
      pagination={(
        <WorkQueuePagination
          page={urlState.page}
          total={data.total}
          limit={data.limit}
          onPageChange={(page) => updateUrlState({ page })}
        />
      )}
    >
      {data.items.length === 0 ? (
        <EmptyState
          title="Inga förslag väntar på beslut."
          description="När nya förslag behöver granskas visas de här. Just nu finns inget som matchar dina filter."
        />
      ) : (
        <ul className="space-y-3" aria-label="Godkännanden">
          {data.items.map((item) => (
            <li key={item.approval_id}>
              <ApprovalItemCard item={item} />
            </li>
          ))}
        </ul>
      )}
    </WorkQueuePageLayout>
  )
}
