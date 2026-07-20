import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useMemo, useState } from "react"
import { useParams } from "react-router-dom"

import { postJson } from "@/api/client"
import { Button } from "@/components/ui/button"
import { CriticalActionDialog } from "@/components/operator/CriticalActionDialog"

type GmailOAuthStatus = {
  connection_state: "not_connected" | "connected" | "reconnect_required" | "connecting" | "error"
  credential_source?: "tenant_oauth" | "platform_env" | null
  connected: boolean
  reconnect_required: boolean
  email?: string | null
  expires_at?: string | null
  scopes?: string | null
  connected_at?: string | null
}

const STATE_LABELS: Record<string, string> = {
  not_connected: "Ej ansluten",
  connected: "Ansluten",
  reconnect_required: "Återanslutning krävs",
  connecting: "Ansluter",
  error: "Fel",
}

function fetchGmailStatus(tenantId: string): Promise<GmailOAuthStatus> {
  return fetch(`/admin/tenants/${encodeURIComponent(tenantId)}/integrations/google_mail/status`, {
    credentials: "include",
  }).then(async (res) => {
    if (!res.ok) {
      throw new Error(`Status HTTP ${res.status}`)
    }
    return res.json() as Promise<GmailOAuthStatus>
  })
}

export function GmailIntegrationPanel({ tenantId }: { tenantId: string }) {
  const queryClient = useQueryClient()
  const [disconnectOpen, setDisconnectOpen] = useState(false)
  const [disconnectError, setDisconnectError] = useState<string>()

  const statusQuery = useQuery({
    queryKey: ["admin", "tenants", tenantId, "gmail-oauth"],
    queryFn: () => fetchGmailStatus(tenantId),
    staleTime: 15_000,
  })

  const connectMutation = useMutation({
    mutationFn: async () => {
      const redirectTarget = `/ops/customers/${tenantId}`
      const res = await postJson<{ authorization_url: string }>(
        `/admin/tenants/${encodeURIComponent(tenantId)}/integrations/google_mail/connect`,
        { redirect_target: redirectTarget },
      )
      return res
    },
    onSuccess: (data) => {
      window.location.href = data.authorization_url
    },
  })

  const disconnectMutation = useMutation({
    mutationFn: async () =>
      postJson(`/admin/tenants/${encodeURIComponent(tenantId)}/integrations/google_mail/disconnect`, {}),
    onSuccess: async () => {
      setDisconnectOpen(false)
      await queryClient.invalidateQueries({ queryKey: ["admin", "tenants", tenantId] })
    },
    onError: (err: unknown) => {
      setDisconnectError(err instanceof Error ? err.message : "Kunde inte koppla från.")
    },
  })

  const status = statusQuery.data
  const label = useMemo(() => {
    if (connectMutation.isPending) return STATE_LABELS.connecting
    if (statusQuery.isError) return STATE_LABELS.error
    return STATE_LABELS[status?.connection_state ?? "not_connected"] ?? status?.connection_state
  }, [connectMutation.isPending, status?.connection_state, statusQuery.isError])

  return (
    <div className="min-w-0 rounded-lg border border-border bg-page px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-body font-medium text-text-primary">Google Gmail</p>
          <p className="text-body-small text-text-secondary">Status: {label}</p>
          {status?.email ? (
            <p className="text-caption text-text-secondary">Konto: {status.email}</p>
          ) : null}
          {status?.credential_source === "platform_env" ? (
            <p className="text-caption text-status-warning">
              Legacy plattforms-credentials — anslut via OAuth för tenant-isolerad drift.
            </p>
          ) : null}
          {status?.reconnect_required ? (
            <p className="text-caption text-status-warning">Token ogiltig — återanslut krävs.</p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={connectMutation.isPending}
            onClick={() => void connectMutation.mutateAsync()}
          >
            {status?.connected ? "Återanslut Google" : "Anslut Google"}
          </Button>
          {status?.connected && status.credential_source === "tenant_oauth" ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                setDisconnectError(undefined)
                setDisconnectOpen(true)
              }}
            >
              Koppla från
            </Button>
          ) : null}
        </div>
      </div>

      <CriticalActionDialog
        open={disconnectOpen}
        title="Koppla från Google Gmail"
        consequence="Detta tar bort tenantens lagrade OAuth-uppgifter i Krowolf. Google-kontot revoke:as inte automatiskt hos Google."
        primaryLabel="Koppla från"
        loading={disconnectMutation.isPending}
        error={disconnectError}
        onClose={() => setDisconnectOpen(false)}
        onConfirm={() => void disconnectMutation.mutateAsync()}
      />
    </div>
  )
}

export function GmailIntegrationPanelRoute() {
  const { tenantId } = useParams<{ tenantId: string }>()
  if (!tenantId) return null
  return <GmailIntegrationPanel tenantId={tenantId} />
}
