import type { ReactNode } from "react"
import { Link, useLocation } from "react-router-dom"

import type { WorkItemReturnState } from "@/customer/navigation/workItemNavigation"
import { cn } from "@/lib/utils"

type WorkItemLinkProps = {
  workItemId: string
  className?: string
  children: ReactNode
}

export function WorkItemLink({
  workItemId,
  className,
  children,
}: WorkItemLinkProps) {
  const location = useLocation()
  const returnState: WorkItemReturnState = {
    from: `${location.pathname}${location.search}`,
  }

  return (
    <Link
      to={`/work/${workItemId}`}
      state={returnState}
      className={cn(
        "inline-flex min-h-11 items-center rounded-md text-brand underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
        className,
      )}
    >
      {children}
    </Link>
  )
}
