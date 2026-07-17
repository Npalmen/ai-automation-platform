import { useQuery } from "@tanstack/react-query"

import { get } from "@/api/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"

type HealthResponse = {
  status: string
  app_name: string
  env: string
}

export function FoundationPage() {
  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: () => get<HealthResponse>("/health"),
  })

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          Krowolf Operations
        </h1>
        <p className="text-sm text-muted-foreground sm:text-base">
          Frontend foundation
        </p>
      </div>

      <section className="grid min-w-0 gap-4 rounded-lg border bg-card p-4 text-card-foreground sm:p-6">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <Badge variant="secondary">Build mode</Badge>
          <span className="break-words text-sm font-mono text-muted-foreground">
            {import.meta.env.MODE}
          </span>
        </div>

        <div className="min-w-0 space-y-2">
          <p className="text-sm font-medium">API health check</p>
          {healthQuery.isLoading ? (
            <p className="break-words text-sm text-muted-foreground">
              Checking /health…
            </p>
          ) : healthQuery.isError ? (
            <p className="break-words text-sm text-destructive">
              Health check unavailable in this environment.
            </p>
          ) : (
            <p className="break-words text-sm text-muted-foreground">
              status={healthQuery.data?.status}, env=
              <span className="font-mono">{healthQuery.data?.env}</span>
            </p>
          )}
        </div>

        <div className="flex min-w-0 flex-wrap gap-3">
          <Button type="button">Foundation ready</Button>
          <Badge>Operator panel v0</Badge>
        </div>
      </section>
    </div>
  )
}
