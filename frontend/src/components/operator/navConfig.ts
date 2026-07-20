import { isRoleAllowed } from "@/features/auth/permissions"
import type { Role } from "@/features/auth/types"

export type NavItem = {
  to: string
  label: string
  end?: boolean
  allowedRoles: readonly Role[]
}

export const NAV_ITEMS: readonly NavItem[] = [
  { to: "/", label: "Översikt", end: true, allowedRoles: ["read_only", "operations", "admin"] },
  { to: "/needs-help", label: "Behöver hjälp", allowedRoles: ["read_only", "operations", "admin"] },
  { to: "/customers", label: "Kunder", allowedRoles: ["read_only", "operations", "admin"] },
  { to: "/incidents", label: "Incidenter", allowedRoles: ["read_only", "operations", "admin"] },
  { to: "/alerts", label: "Larm", allowedRoles: ["read_only", "operations", "admin"] },
  { to: "/usage", label: "Användning", allowedRoles: ["read_only", "operations", "admin"] },
  { to: "/system", label: "System", allowedRoles: ["operations", "admin"] },
]

export function visibleNavItemsForRole(role: Role | undefined): NavItem[] {
  return NAV_ITEMS.filter((item) => isRoleAllowed(role, item.allowedRoles))
}
