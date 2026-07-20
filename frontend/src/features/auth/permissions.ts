import type { Role } from "./types"

/** Higher level inherits all navigation/access of lower roles. */
export const ROLE_LEVEL = {
  read_only: 10,
  operations: 20,
  admin: 30,
  super_admin: 40,
} as const satisfies Record<Role, number>

export function roleLevel(role: Role | string | undefined): number | null {
  if (!role || !(role in ROLE_LEVEL)) {
    return null
  }
  return ROLE_LEVEL[role as Role]
}

/**
 * True when `role` meets at least one minimum role in `allowedRoles` via hierarchy.
 * Example: allowedRoles ["admin"] also permits super_admin.
 */
export function isRoleAllowed(
  role: Role | undefined,
  allowedRoles: readonly Role[],
): boolean {
  const actual = roleLevel(role)
  if (actual === null || allowedRoles.length === 0) {
    return false
  }
  const minRequired = Math.min(
    ...allowedRoles.map((allowed) => ROLE_LEVEL[allowed]),
  )
  return actual >= minRequired
}

export const ROLE_LABELS = {
  read_only: "Läsbehörighet",
  operations: "Drift",
  admin: "Admin",
  super_admin: "Superadmin",
} satisfies Record<Role, string>

export const ENVIRONMENT_LABELS = {
  local: "Lokal",
  test: "Test",
  production: "Produktion",
} as const
