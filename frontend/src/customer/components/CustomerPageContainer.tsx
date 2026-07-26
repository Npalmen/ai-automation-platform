import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

type CustomerPageContainerProps = {
  children: ReactNode
  className?: string
}

export function CustomerPageContainer({
  children,
  className,
}: CustomerPageContainerProps) {
  return (
    <div className={cn("mx-auto w-full max-w-6xl min-w-0 px-4 py-6 md:px-6", className)}>
      {children}
    </div>
  )
}
