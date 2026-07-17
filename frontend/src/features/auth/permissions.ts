import type { Role } from "./types"

export function isRoleAllowed(
  role: Role | undefined,
  allowedRoles: readonly Role[],
): boolean {
  if (!role) {
    return false
  }
  return allowedRoles.includes(role)
}

export const ROLE_LABELS = {
  read_only: "Läsbehörighet",
  operations: "Drift",
  admin: "Admin",
} satisfies Record<Role, string>

export const ENVIRONMENT_LABELS = {
  local: "Lokal",
  test: "Test",
  production: "Produktion",
} as const
