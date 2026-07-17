import { Navigate, useLocation } from "react-router-dom"

import { LoadingState } from "@/components/operator/LoadingState"

import { useAuth } from "./AuthProvider"

type RequireAuthProps = {
  children: React.ReactNode
}

export function RequireAuth({ children }: RequireAuthProps) {
  const { auth } = useAuth()
  const location = useLocation()

  if (auth.status === "loading") {
    return (
      <div className="min-h-screen bg-page p-4 sm:p-6">
        <LoadingState label="Kontrollerar session…" />
      </div>
    )
  }

  if (auth.status === "unauthenticated") {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: location.pathname }}
      />
    )
  }

  return children
}
