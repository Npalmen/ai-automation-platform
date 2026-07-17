import type { Role } from "@/features/auth/types"

export type RoutePolicy = {
  path: string
  allowedRoles: readonly Role[]
}

export const ROUTE_POLICIES: readonly RoutePolicy[] = [
  { path: "/", allowedRoles: ["read_only", "operations", "admin"] },
  { path: "/needs-help", allowedRoles: ["read_only", "operations", "admin"] },
  { path: "/needs-help/:itemId", allowedRoles: ["read_only", "operations", "admin"] },
  { path: "/customers", allowedRoles: ["read_only", "operations", "admin"] },
  { path: "/customers/:tenantId", allowedRoles: ["read_only", "operations", "admin"] },
  { path: "/incidents", allowedRoles: ["read_only", "operations", "admin"] },
  { path: "/usage", allowedRoles: ["read_only", "operations", "admin"] },
  { path: "/system", allowedRoles: ["operations", "admin"] },
  { path: "/foundation", allowedRoles: ["admin"] },
  { path: "/design-reference", allowedRoles: ["admin"] },
]

function routeAllowsRole(route: RoutePolicy, role: Role): boolean {
  return route.allowedRoles.includes(role)
}

export const ROUTE_POLICY_COVERAGE: Record<Role, readonly RoutePolicy[]> = {
  read_only: ROUTE_POLICIES.filter((route) => routeAllowsRole(route, "read_only")),
  operations: ROUTE_POLICIES.filter((route) =>
    routeAllowsRole(route, "operations"),
  ),
  admin: ROUTE_POLICIES.filter((route) => routeAllowsRole(route, "admin")),
}
