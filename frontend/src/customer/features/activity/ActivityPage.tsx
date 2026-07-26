import { useQuery } from "@tanstack/react-query"
import { useCallback, useEffect, useMemo } from "react"
import { useSearchParams } from "react-router-dom"

import { EmptyState } from "@/components/shared/EmptyState"
import { ErrorState } from "@/components/shared/ErrorState"
import { LoadingState } from "@/components/shared/LoadingState"
import { useCustomerAuth } from "@/customer/auth/CustomerAuthProvider"
import {
  ActivityItemCard,
  groupActivitiesByDate,
} from "@/customer/features/activity/ActivityItemCard"
import {
  ACTIVITY_TYPE_FILTERS,
  activityOffset,
  buildActivitySearchParams,
  normalizePageForTotal,
  parseActivityUrlState,
} from "@/customer/features/activity/activityUrlState"
import { QueueResultSummary } from "@/customer/features/work-queues/QueueResultSummary"
import { WorkQueuePageLayout } from "@/customer/features/work-queues/WorkQueuePageLayout"
import { WorkQueuePagination } from "@/customer/features/work-queues/WorkQueuePagination"
import { WorkQueuePartialError } from "@/customer/features/work-queues/WorkQueuePartialError"
import { WorkQueueToolbar } from "@/customer/features/work-queues/WorkQueueToolbar"
import { WORK_QUEUE_PAGE_SIZE } from "@/customer/features/work-queues/workQueueConstants"
import type { ActivityListParams } from "@/customer/types/activity"

export function buildActivityQueryKey(params: ActivityListParams) {
  return ["customer-workspace", "activity", params] as const
}

export function ActivityPage() {
  const { dataSource } = useCustomerAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const urlState = useMemo(
    () => parseActivityUrlState(searchParams),
    [searchParams],
  )

  const queryParams = useMemo<ActivityListParams>(
    () => ({
      type: urlState.type,
      limit: WORK_QUEUE_PAGE_SIZE,
      offset: activityOffset(urlState.page),
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
    queryKey: buildActivityQueryKey(queryParams),
    queryFn: () => dataSource.listActivity(queryParams),
    retry: 1,
    refetchOnWindowFocus: false,
  })

  const updateUrlState = useCallback(
    (next: Partial<typeof urlState>) => {
      const merged = { ...urlState, ...next }
      setSearchParams(buildActivitySearchParams(merged), { replace: false })
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
        title="Aktivitet"
        description="Vad systemet har upptäckt, förberett och utfört åt er."
      >
        <LoadingState label="Laddar aktivitet…" rows={4} />
      </WorkQueuePageLayout>
    )
  }

  if (isError || !data) {
    return (
      <WorkQueuePageLayout
        title="Aktivitet"
        description="Vad systemet har upptäckt, förberett och utfört åt er."
      >
        <ErrorState
          title="Aktiviteten kunde inte laddas"
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

  const grouped = groupActivitiesByDate(data.items)

  return (
    <WorkQueuePageLayout
      title="Aktivitet"
      description="Vad systemet har upptäckt, förberett och utfört åt er."
      toolbar={(
        <WorkQueueToolbar>
          <div className="min-w-0">
            <label
              htmlFor="activity-type-filter"
              className="mb-1 block text-body-small font-medium text-text-primary"
            >
              Typ
            </label>
            <select
              id="activity-type-filter"
              className="min-h-11 w-full min-w-[10rem] rounded-md border border-border bg-surface px-3 text-body text-text-primary"
              value={urlState.type}
              onChange={(event) =>
                updateUrlState({
                  type: event.target.value as ActivityListParams["type"],
                  page: 1,
                })}
            >
              {ACTIVITY_TYPE_FILTERS.map((option) => (
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
          title="Ingen aktivitet matchar ditt val."
          description="Nya händelser visas här när systemet arbetar vidare."
        />
      ) : (
        <div className="space-y-6">
          {grouped.map((group) => (
            <section key={group.dateLabel} aria-label={group.dateLabel}>
              <h2 className="mb-3 text-section-title text-text-primary">
                {group.dateLabel}
              </h2>
              <ul className="space-y-3">
                {group.items.map((item, index) => (
                  <li key={`${item.at}-${item.label}-${index}`}>
                    <ActivityItemCard item={item} />
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </WorkQueuePageLayout>
  )
}
