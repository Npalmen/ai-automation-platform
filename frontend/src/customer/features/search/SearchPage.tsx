import { useQuery } from "@tanstack/react-query"
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react"
import { useSearchParams } from "react-router-dom"

import { EmptyState } from "@/components/shared/EmptyState"
import { ErrorState } from "@/components/shared/ErrorState"
import { LoadingState } from "@/components/shared/LoadingState"
import { useCustomerAuth } from "@/customer/auth/CustomerAuthProvider"
import {
  buildSearchUrlParams,
  hasInvalidSearchDateRange,
  normalizePageForTotal,
  parseSearchUrlState,
  searchOffset,
  WORK_QUEUE_PAGE_SIZE,
  WORK_QUEUE_SORT_OPTIONS,
} from "@/customer/features/search/searchUrlState"
import { buildWorkItemsQueryKey } from "@/customer/features/work-queues/WorkItemsQueuePage"
import { QueueResultSummary } from "@/customer/features/work-queues/QueueResultSummary"
import { WorkQueueList } from "@/customer/features/work-queues/WorkQueueList"
import { WorkQueuePageLayout } from "@/customer/features/work-queues/WorkQueuePageLayout"
import { WorkQueuePagination } from "@/customer/features/work-queues/WorkQueuePagination"
import { WorkQueuePartialError } from "@/customer/features/work-queues/WorkQueuePartialError"
import { WorkQueueSortControl } from "@/customer/features/work-queues/WorkQueueSortControl"
import { WorkQueueStatusFilter } from "@/customer/features/work-queues/WorkQueueStatusFilter"
import { WorkQueueToolbar } from "@/customer/features/work-queues/WorkQueueToolbar"
import type { WorkItemListParams } from "@/customer/types/work-items"

const SEARCH_TYPE_FILTERS = [
  { value: "all" as const, label: "Alla typer" },
  { value: "lead" as const, label: "Leads" },
  { value: "support" as const, label: "Kundfrågor" },
  { value: "needs_help" as const, label: "Behöver hjälp" },
]

export function SearchPage() {
  const { dataSource } = useCustomerAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const urlState = useMemo(
    () => parseSearchUrlState(searchParams),
    [searchParams],
  )
  const [draftQuery, setDraftQuery] = useState(urlState.q)
  const invalidDateRange = hasInvalidSearchDateRange(urlState)
  const hasQuery = urlState.q.length > 0

  useEffect(() => {
    setDraftQuery(urlState.q)
  }, [urlState.q])

  const queryParams = useMemo<WorkItemListParams | null>(() => {
    if (!hasQuery || invalidDateRange) return null
    return {
      type: urlState.type,
      status: urlState.status === "all" ? undefined : urlState.status,
      sort: urlState.sort,
      order: urlState.order,
      q: urlState.q,
      from: urlState.from || undefined,
      to: urlState.to || undefined,
      limit: WORK_QUEUE_PAGE_SIZE,
      offset: searchOffset(urlState.page),
    }
  }, [hasQuery, invalidDateRange, urlState])

  const {
    data,
    isLoading,
    isError,
    isFetching,
    refetch,
  } = useQuery({
    queryKey: queryParams ? buildWorkItemsQueryKey(queryParams) : ["customer-workspace", "search", "idle"],
    queryFn: () => dataSource.listWorkItems(queryParams!),
    enabled: Boolean(queryParams),
    retry: 1,
    refetchOnWindowFocus: false,
  })

  const updateUrlState = useCallback(
    (next: Partial<typeof urlState>) => {
      const merged = { ...urlState, ...next }
      setSearchParams(buildSearchUrlParams(merged), { replace: false })
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

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = draftQuery.trim()
    if (!trimmed) return
    updateUrlState({ q: trimmed, page: 1 })
  }

  function clearFilters() {
    updateUrlState({
      type: "all",
      status: "all",
      from: "",
      to: "",
      page: 1,
    })
  }

  const searchForm = (
    <form onSubmit={handleSubmit} role="search" className="mb-4">
      <label htmlFor="global-search" className="mb-1 block text-body-small font-medium text-text-primary">
        Sök
      </label>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          id="global-search"
          type="search"
          value={draftQuery}
          onChange={(event) => setDraftQuery(event.target.value)}
          placeholder="Sök efter ärende, kund eller e-postadress"
          className="min-h-11 flex-1 rounded-md border border-border bg-surface px-3 text-body text-text-primary"
        />
        <button
          type="submit"
          className="inline-flex min-h-11 items-center justify-center rounded-md bg-brand px-4 text-body font-medium text-brand-foreground"
        >
          Sök
        </button>
      </div>
    </form>
  )

  if (!hasQuery) {
    return (
      <WorkQueuePageLayout
        title="Sökning"
        description="Hitta ärenden, kunder och e-postadresser i arbetsytan."
      >
        {searchForm}
        <EmptyState
          title="Sök efter ett ärende, en kund eller en e-postadress."
          description="Ange minst ett sökord och tryck Sök för att se resultat."
        />
      </WorkQueuePageLayout>
    )
  }

  if (invalidDateRange) {
    return (
      <WorkQueuePageLayout
        title="Sökning"
        description="Hitta ärenden, kunder och e-postadresser i arbetsytan."
      >
        {searchForm}
        <div
          className="rounded-lg border border-status-danger/30 bg-status-danger/5 p-4 text-body text-text-secondary"
          role="alert"
          id="search-date-range-error"
        >
          Startdatum kan inte vara senare än slutdatum. Justera datumfiltren och försök igen.
        </div>
      </WorkQueuePageLayout>
    )
  }

  if (isLoading) {
    return (
      <WorkQueuePageLayout
        title="Sökning"
        description={`Resultat för “${urlState.q}”`}
      >
        {searchForm}
        <LoadingState label="Söker…" rows={4} />
      </WorkQueuePageLayout>
    )
  }

  if (isError || !data) {
    return (
      <WorkQueuePageLayout
        title="Sökning"
        description={`Resultat för “${urlState.q}”`}
      >
        {searchForm}
        <ErrorState
          title="Sökningen kunde inte slutföras"
          description="Försök igen om en stund."
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
      title="Sökning"
      description={`Resultat för “${urlState.q}”`}
      toolbar={(
        <>
          {searchForm}
          <WorkQueueToolbar>
            <div className="min-w-0">
              <label htmlFor="search-type-filter" className="mb-1 block text-body-small font-medium text-text-primary">
                Typ
              </label>
              <select
                id="search-type-filter"
                className="min-h-11 w-full min-w-[10rem] rounded-md border border-border bg-surface px-3 text-body text-text-primary"
                value={urlState.type}
                onChange={(event) =>
                  updateUrlState({
                    type: event.target.value as typeof urlState.type,
                    page: 1,
                  })}
              >
                {SEARCH_TYPE_FILTERS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
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
            <div className="min-w-0">
              <label htmlFor="search-from" className="mb-1 block text-body-small font-medium text-text-primary">
                Från datum
              </label>
              <input
                id="search-from"
                type="date"
                value={urlState.from}
                onChange={(event) =>
                  updateUrlState({ from: event.target.value, page: 1 })}
                className="min-h-11 w-full rounded-md border border-border bg-surface px-3 text-body text-text-primary"
              />
            </div>
            <div className="min-w-0">
              <label htmlFor="search-to" className="mb-1 block text-body-small font-medium text-text-primary">
                Till datum
              </label>
              <input
                id="search-to"
                type="date"
                value={urlState.to}
                onChange={(event) =>
                  updateUrlState({ to: event.target.value, page: 1 })}
                className="min-h-11 w-full rounded-md border border-border bg-surface px-3 text-body text-text-primary"
                aria-describedby={invalidDateRange ? "search-date-range-error" : undefined}
              />
            </div>
            <div className="flex items-end">
              <button
                type="button"
                className="inline-flex min-h-11 items-center rounded-md border border-border bg-surface px-4 text-body font-medium text-text-primary hover:bg-surface-subtle"
                onClick={clearFilters}
              >
                Rensa filter
              </button>
            </div>
          </WorkQueueToolbar>
        </>
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
        emptyTitle="Inga ärenden matchar din sökning."
        emptyDescription="Prova att ändra sökord eller rensa filter."
      />
    </WorkQueuePageLayout>
  )
}
