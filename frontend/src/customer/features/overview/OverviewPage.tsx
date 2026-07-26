import { useQuery } from "@tanstack/react-query"

import { ErrorState } from "@/components/shared/ErrorState"
import { LoadingState } from "@/components/shared/LoadingState"
import { useCustomerAuth } from "@/customer/auth/CustomerAuthProvider"
import { CustomerPageContainer } from "@/customer/components/CustomerPageContainer"
import { OverviewHeader } from "@/customer/features/overview/OverviewHeader"
import { OverviewPartialError } from "@/customer/features/overview/OverviewPartialError"
import { OverviewSummarySection } from "@/customer/features/overview/OverviewSummary"
import { PriorityWorkList } from "@/customer/features/overview/PriorityWorkList"

export const OVERVIEW_QUERY_KEY = ["customer-workspace", "overview"] as const

export function OverviewPage() {
  const { auth, dataSource } = useCustomerAuth()
  const {
    data,
    isLoading,
    isError,
    isFetching,
    refetch,
  } = useQuery({
    queryKey: OVERVIEW_QUERY_KEY,
    queryFn: () => dataSource.getOverview(),
    retry: 1,
    refetchOnWindowFocus: false,
  })

  if (isLoading) {
    return (
      <CustomerPageContainer>
        <OverviewHeader
          companyName={auth.context.company_name}
          lastUpdatedAt={null}
        />
        <LoadingState label="Laddar översikten…" rows={5} />
      </CustomerPageContainer>
    )
  }

  if (isError || !data) {
    return (
      <CustomerPageContainer>
        <OverviewHeader
          companyName={auth.context.company_name}
          lastUpdatedAt={null}
        />
        <ErrorState
          title="Översikten kunde inte laddas"
          description="Försök igen om en stund. Om problemet kvarstår kan du kontakta support."
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

  const hideValueEstimate = data.partial_errors.some(
    (error) => error.section === "value_estimate",
  )

  return (
    <CustomerPageContainer>
      <OverviewHeader
        companyName={auth.context.company_name}
        lastUpdatedAt={data.last_updated_at}
        isRefreshing={isFetching && !isLoading}
      />
      <OverviewPartialError errors={data.partial_errors} />
      <OverviewSummarySection
        summary={data.summary}
        hideValueEstimate={hideValueEstimate}
      />
      <PriorityWorkList items={data.priority_work_items} />
    </CustomerPageContainer>
  )
}
