import type { WorkItemType } from "@/customer/types/work-items"

export type WorkItemReturnState = {
  from?: string
}

export function isSafeAppReturnPath(path: string | undefined): path is string {
  if (!path) return false
  if (!path.startsWith("/")) return false
  if (path.startsWith("//")) return false
  if (path.includes("://")) return false
  return path === "/" || path.startsWith("/leads")
    || path.startsWith("/support")
    || path.startsWith("/approvals")
    || path.startsWith("/needs-help")
    || path.startsWith("/activity")
    || path.startsWith("/search")
}

export function fallbackRouteForWorkItemType(type: WorkItemType): string {
  switch (type) {
    case "lead":
      return "/leads"
    case "support":
      return "/support"
    case "needs_help":
      return "/needs-help"
    default:
      return "/"
  }
}

export function resolveWorkItemBackPath(
  returnState: WorkItemReturnState | null | undefined,
  workItemType: WorkItemType,
): string {
  if (returnState?.from && isSafeAppReturnPath(returnState.from)) {
    return returnState.from
  }
  return fallbackRouteForWorkItemType(workItemType)
}
