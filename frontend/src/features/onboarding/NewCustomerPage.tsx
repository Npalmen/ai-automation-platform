import { useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"

import { ErrorState } from "@/components/operator/ErrorState"
import { PageHeader } from "@/components/operator/PageHeader"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/features/auth/AuthProvider"

import { formatOnboardingError, useCreateOnboardingMutation } from "./mutations"

const inputClassName =
  "min-h-11 w-full rounded-md border border-border bg-page px-3 text-body text-text-primary"

export function NewCustomerPage() {
  const navigate = useNavigate()
  const { auth } = useAuth()
  const createMutation = useCreateOnboardingMutation()
  const [companyName, setCompanyName] = useState("")
  const [slug, setSlug] = useState("")

  const role = auth.status === "authenticated" ? auth.operator.role : null
  const canCreate = role === "operations" || role === "admin"
  const canSubmit =
    companyName.trim().length > 0 && slug.trim().length >= 2 && !createMutation.isPending

  const suggestedSlug = useMemo(() => {
    return companyName
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/-{2,}/g, "-")
      .replace(/^-|-$/g, "")
  }, [companyName])

  if (!canCreate) {
    return (
      <ErrorState
        title="Behörighet saknas"
        description="Endast drift och admin kan starta kundonboarding."
        recommendedAction="Kontakta en administratör."
      />
    )
  }

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <PageHeader
        title="Ny kund"
        description="Starta standardiserad onboarding. Ingen API-nyckel skapas automatiskt."
      />

      <form
        className="mx-auto w-full max-w-xl space-y-4 rounded-lg border border-border bg-surface p-6"
        onSubmit={(event) => {
          event.preventDefault()
          if (!canSubmit) return
          createMutation.mutate(
            {
              company_name: companyName.trim(),
              slug: slug.trim() || suggestedSlug,
              timezone: "Europe/Stockholm",
              language: "sv",
            },
            {
              onSuccess: (session) => {
                navigate(
                  `/customers/${encodeURIComponent(session.tenant_id)}/onboarding`,
                  { replace: true },
                )
              },
            },
          )
        }}
      >
        <label className="block space-y-2">
          <span className="text-label text-text-primary">Företagsnamn</span>
          <input
            className={inputClassName}
            value={companyName}
            onChange={(event) => setCompanyName(event.target.value)}
            required
          />
        </label>
        <label className="block space-y-2">
          <span className="text-label text-text-primary">Slug</span>
          <input
            className={inputClassName}
            value={slug}
            onChange={(event) => setSlug(event.target.value)}
            placeholder={suggestedSlug || "foretag-slug"}
            required
          />
          <p className="text-body-small text-text-secondary">
            Används vid aktivering som bekräftelsefras.
          </p>
        </label>
        {createMutation.isError ? (
          <p className="text-body-small text-status-danger" role="alert">
            {formatOnboardingError(createMutation.error)}
          </p>
        ) : null}
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
          <Button type="button" variant="outline" onClick={() => navigate("/customers")}>
            Avbryt
          </Button>
          <Button type="submit" disabled={!canSubmit}>
            {createMutation.isPending ? "Skapar…" : "Starta onboarding"}
          </Button>
        </div>
      </form>
    </div>
  )
}
