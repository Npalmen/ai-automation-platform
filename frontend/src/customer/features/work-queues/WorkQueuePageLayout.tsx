import type { ReactNode } from "react"

import { CustomerPageContainer } from "@/customer/components/CustomerPageContainer"
import { CustomerPageHeader } from "@/customer/components/CustomerPageHeader"

type WorkQueuePageLayoutProps = {
  title: string
  description: string
  toolbar?: ReactNode
  summary?: ReactNode
  partialError?: ReactNode
  children: ReactNode
  pagination?: ReactNode
}

export function WorkQueuePageLayout({
  title,
  description,
  toolbar,
  summary,
  partialError,
  children,
  pagination,
}: WorkQueuePageLayoutProps) {
  return (
    <CustomerPageContainer>
      <CustomerPageHeader title={title} description={description} />
      {toolbar}
      {summary}
      {partialError}
      <section aria-label={title} className="space-y-4">
        {children}
      </section>
      {pagination ? <div className="mt-6">{pagination}</div> : null}
    </CustomerPageContainer>
  )
}
