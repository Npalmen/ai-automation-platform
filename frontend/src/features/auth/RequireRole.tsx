import type { Role } from "./types"
import { ForbiddenPage } from "./ForbiddenPage"
import { useAuth } from "./AuthProvider"
import { isRoleAllowed } from "./permissions"

type RequireRoleProps = {
  allowedRoles: readonly Role[]
  children: React.ReactNode
}

export function RequireRole({ allowedRoles, children }: RequireRoleProps) {
  const { auth } = useAuth()

  if (auth.status !== "authenticated") {
    return null
  }

  if (!isRoleAllowed(auth.operator.role, allowedRoles)) {
    return <ForbiddenPage />
  }

  return children
}
