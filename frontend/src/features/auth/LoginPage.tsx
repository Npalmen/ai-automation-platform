import { useId, useState, type FormEvent } from "react"
import { Navigate, useLocation } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { LoadingState } from "@/components/operator/LoadingState"

import { useAuth } from "./AuthProvider"

const GENERIC_LOGIN_ERROR =
  "Inloggningen misslyckades. Kontrollera uppgifterna och försök igen."

export function LoginPage() {
  const { auth, login } = useAuth()
  const location = useLocation()
  const usernameId = useId()
  const passwordId = useId()
  const errorId = useId()

  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [hasError, setHasError] = useState(false)

  const redirectTo =
    (location.state as { from?: string } | null)?.from ?? "/"

  if (auth.status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-page px-4 py-8">
        <LoadingState label="Kontrollerar session…" rows={2} className="w-full max-w-md" />
      </div>
    )
  }

  if (auth.status === "authenticated") {
    return <Navigate to={redirectTo} replace />
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setHasError(false)
    setIsSubmitting(true)
    try {
      await login(username.trim(), password)
    } catch {
      setHasError(true)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-page px-4 py-8 sm:px-6">
      <div className="w-full max-w-md space-y-6 rounded-lg border border-border bg-surface p-6 shadow-sm">
        <header className="space-y-2">
          <p className="text-label font-medium uppercase tracking-wide text-text-secondary">
            Intern operatörsåtkomst
          </p>
          <h1 className="text-page-title font-semibold text-text-primary">
            Logga in
          </h1>
          <p className="text-body text-text-secondary">
            Endast behörig Krowolf-personal. Den här panelen är inte en
            kundportal.
          </p>
        </header>

        <form className="space-y-4" onSubmit={handleSubmit} noValidate>
          <div className="space-y-2">
            <label
              htmlFor={usernameId}
              className="text-label font-medium text-text-primary"
            >
              Användarnamn
            </label>
            <input
              id={usernameId}
              name="username"
              type="text"
              autoComplete="username"
              required
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="min-h-11 w-full rounded-md border border-border bg-background px-3 text-body text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>

          <div className="space-y-2">
            <label
              htmlFor={passwordId}
              className="text-label font-medium text-text-primary"
            >
              Lösenord
            </label>
            <input
              id={passwordId}
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="min-h-11 w-full rounded-md border border-border bg-background px-3 text-body text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>

          {hasError ? (
            <p
              id={errorId}
              role="alert"
              className="rounded-md border border-status-danger/30 bg-status-danger/10 px-3 py-2 text-body text-text-primary"
            >
              {GENERIC_LOGIN_ERROR}
            </p>
          ) : null}

          <Button
            type="submit"
            className="min-h-11 w-full"
            disabled={isSubmitting}
            aria-describedby={hasError ? errorId : undefined}
          >
            {isSubmitting ? "Loggar in…" : "Logga in"}
          </Button>
        </form>
      </div>
    </div>
  )
}
