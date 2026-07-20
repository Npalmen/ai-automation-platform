import type { Role } from "@/features/auth/types"
import { isRoleAllowed } from "@/features/auth/permissions"

export type RoutePolicy = {
  path: string
  allowedRoles: readonly Role[]
}

export const ROUTE_POLICIES: readonly RoutePolicy[] = [
  { path: "/", allowedRoles: ["read_only", "operations", "admin", "super_admin"] },
  { path: "/needs-help", allowedRoles: ["read_only", "operations", "admin", "super_admin"] },
  { path: "/needs-help/:itemId", allowedRoles: ["read_only", "operations", "admin", "super_admin"] },
  { path: "/customers", allowedRoles: ["read_only", "operations", "admin", "super_admin"] },
  { path: "/customers/:tenantId", allowedRoles: ["read_only", "operations", "admin", "super_admin"] },
  { path: "/customers/new", allowedRoles: ["operations", "admin", "super_admin"] },
  { path: "/customers/:tenantId/onboarding", allowedRoles: ["operations", "admin", "super_admin"] },
  { path: "/incidents", allowedRoles: ["read_only", "operations", "admin", "super_admin"] },
  { path: "/alerts", allowedRoles: ["read_only", "operations", "admin", "super_admin"] },
  { path: "/alerts/:alertId", allowedRoles: ["read_only", "operations", "admin", "super_admin"] },
  { path: "/digests", allowedRoles: ["operations", "admin", "super_admin"] },
  { path: "/usage", allowedRoles: ["read_only", "operations", "admin", "super_admin"] },
  { path: "/system", allowedRoles: ["operations", "admin", "super_admin"] },
  { path: "/foundation", allowedRoles: ["admin", "super_admin"] },
  { path: "/design-reference", allowedRoles: ["admin", "super_admin"] },
]

function routeAllowsRole(route: RoutePolicy, role: Role): boolean {
  return isRoleAllowed(role, route.allowedRoles)
}

export const ROUTE_POLICY_COVERAGE: Record<Role, readonly RoutePolicy[]> = {
  read_only: ROUTE_POLICIES.filter((route) => routeAllowsRole(route, "read_only")),
  operations: ROUTE_POLICIES.filter((route) =>
    routeAllowsRole(route, "operations"),
  ),
  admin: ROUTE_POLICIES.filter((route) => routeAllowsRole(route, "admin")),
  super_admin: ROUTE_POLICIES.filter((route) => routeAllowsRole(route, "super_admin")),
}
