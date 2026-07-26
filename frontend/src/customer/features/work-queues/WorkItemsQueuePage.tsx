import { useQuery } from "@tanstack/react-query"
import { useCallback, useEffect, useMemo } from "react"
import { useSearchParams } from "react-router-dom"

import { ErrorState } from "@/components/shared/ErrorState"
import { LoadingState } from "@/components/shared/LoadingState"
import { useCustomerAuth } from "@/customer/auth/CustomerAuthProvider"
import { QueueResultSummary } from "@/customer/features/work-queues/QueueResultSummary"
import {
  WORK_QUEUE_PAGE_SIZE,
  WORK_QUEUE_SORT_OPTIONS,
} from "@/customer/features/work-queues/workQueueConstants"
import { WorkQueueList } from "@/customer/features/work-queues/WorkQueueList"
import { WorkQueuePageLayout } from "@/customer/features/work-queues/WorkQueuePageLayout"
import { WorkQueuePagination } from "@/customer/features/work-queues/WorkQueuePagination"
import { WorkQueuePartialError } from "@/customer/features/work-queues/WorkQueuePartialError"
import { WorkQueueSortControl } from "@/customer/features/work-queues/WorkQueueSortControl"
import { WorkQueueStatusFilter } from "@/customer/features/work-queues/WorkQueueStatusFilter"
import { WorkQueueToolbar } from "@/customer/features/work-queues/WorkQueueToolbar"
import {
  buildWorkQueueSearchParams,
  parseWorkQueueUrlState,
  workQueueOffset,
  normalizePageForTotal,
} from "@/customer/features/work-queues/workQueueUrlState"
import type { WorkItemListParams } from "@/customer/types/work-items"

export type WorkItemsQueueConfig = {
  title: string
  description: string
  itemType: "lead" | "support" | "needs_help"
  emptyTitle: string
  emptyDescription: string
}

export function buildWorkItemsQueryKey(params: WorkItemListParams) {
  return ["customer-workspace", "work-items", params] as const
}

export function WorkItemsQueuePage({ config }: { config: WorkItemsQueueConfig }) {
  const { dataSource } = useCustomerAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const urlState = useMemo(
    () => parseWorkQueueUrlState(searchParams),
    [searchParams],
  )

  const queryParams = useMemo<WorkItemListParams>(
    () => ({
      type: config.itemType,
      status: urlState.status === "all" ? undefined : urlState.status,
      sort: urlState.sort,
      order: urlState.order,
      limit: WORK_QUEUE_PAGE_SIZE,
      offset: workQueueOffset(urlState.page),
    }),
    [config.itemType, urlState],
  )

  const {
    data,
    isLoading,
    isError,
    isFetching,
    refetch,
  } = useQuery({
    queryKey: buildWorkItemsQueryKey(queryParams),
    queryFn: () => dataSource.listWorkItems(queryParams),
    retry: 1,
    refetchOnWindowFocus: false,
  })

  const updateUrlState = useCallback(
    (next: Partial<typeof urlState>) => {
      const merged = { ...urlState, ...next }
      setSearchParams(buildWorkQueueSearchParams(merged), { replace: false })
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

  const currentSort = useMemo(
    () =>
      WORK_QUEUE_SORT_OPTIONS.find(
        (option) =>
          option.sort === urlState.sort && option.order === urlState.order,
      ) ?? WORK_QUEUE_SORT_OPTIONS[0],
    [urlState.order, urlState.sort],
  )

  if (isLoading) {
    return (
      <WorkQueuePageLayout title={config.title} description={config.description}>
        <LoadingState label={`Laddar ${config.title.toLowerCase()}…`} rows={4} />
      </WorkQueuePageLayout>
    )
  }

  if (isError || !data) {
    return (
      <WorkQueuePageLayout title={config.title} description={config.description}>
        <ErrorState
          title={`${config.title} kunde inte laddas`}
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
      title={config.title}
      description={config.description}
      toolbar={(
        <WorkQueueToolbar>
          <WorkQueueStatusFilter
            value={urlState.status}
            onChange={(status) => updateUrlState({ status, page: 1 })}
          />
          <WorkQueueSortControl
            value={currentSort}
            onChange={(option) =>
              updateUrlState({
                sort: option.sort,
                order: option.order,
                page: 1,
              })}
          />
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
      <WorkQueueList
        items={data.items}
        linkItems
        emptyTitle={config.emptyTitle}
        emptyDescription={config.emptyDescription}
      />
    </WorkQueuePageLayout>
  )
}
