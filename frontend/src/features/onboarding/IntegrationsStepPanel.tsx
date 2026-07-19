import { useIntegrationsStepQuery } from "./queries"
import {
  useConnectIntegrationMutation,
  useLocalUnlinkIntegrationMutation,
  usePatchExternalRoutingMutation,
  usePatchIntegrationsMutation,
  usePreviewExternalRoutingMutation,
  useResetExternalRoutingMutation,
  useUnrequestIntegrationMutation,
  useVerifyIntegrationMutation,
} from "./mutations"
import type { IntegrationLifecycleItem } from "./types"
import { CriticalActionDialog } from "@/components/operator/CriticalActionDialog"
import { ErrorState } from "@/components/operator/ErrorState"
import { LoadingState } from "@/components/operator/LoadingState"
import { StatusBadge } from "@/components/operator/StatusBadge"
import { Button } from "@/components/ui/button"
import { useEffect, useState } from "react"

type Props = {
  sessionId: string
  tenantId: string
  version: number
  canWrite: boolean
  oauthNotice: string | null
}

const ERROR_COPY: Record<string, string> = {
  not_connected: "Inte ansluten — koppla integrationen först.",
  token_expired: "Token har gått ut — återanslut.",
  api_read_failed: "API-läsning misslyckades.",
  board_read_failed: "Kunde inte läsa Monday-brädet.",
  metadata_read_failed: "Kunde inte läsa kalkylbladets metadata.",
  label_invalid: "Ogiltig Gmail-label.",
}

function lifecycleVariant(status: string): "healthy" | "warning" | "critical" | "unknown" {
  if (status === "verified" || status === "configured_not_running") return "healthy"
  if (status === "authorization_required" || status === "connected") return "warning"
  if (status === "blocked") return "critical"
  return "unknown"
}

function IntegrationMeta({ item }: { item: IntegrationLifecycleItem }) {
  const errorCopy = item.verification_error_code
    ? ERROR_COPY[item.verification_error_code] ?? item.verification_error_code
    : null

  return (
    <div className="mt-2 space-y-1 text-body-small text-text-secondary">
      <p>
        Begärd: {item.requested ? "ja" : "nej"} · Konfigurerad: {item.configured ? "ja" : "nej"} ·
        Ansluten: {item.connected ? "ja" : "nej"} · Verifierad: {item.verified ? "ja" : "nej"}
      </p>
      {item.verified_at ? (
        <p>Senast verifierad: {new Date(item.verified_at).toLocaleString("sv-SE")}</p>
      ) : null}
      {item.freshness_max_hours ? (
        <p>Freshness: max {item.freshness_max_hours} timmar</p>
      ) : null}
      {errorCopy ? <p className="text-status-warning">Fel: {errorCopy}</p> : null}
      {item.gmail_classification ? (
        <ul className="list-inside list-disc">
          <li>Label/query: {item.gmail_classification.label_query ?? "—"}</li>
          <li>Plattformscredential: {item.gmail_classification.platform_credential}</li>
          <li>Tenant mailbox/label: {item.gmail_classification.tenant_mailbox_access}</li>
          <li>Live intake: {item.gmail_classification.live_intake}</li>
          <li>Capability operational: {item.gmail_classification.capability_operational ? "ja" : "nej"}</li>
        </ul>
      ) : null}
    </div>
  )
}

export function IntegrationsStepPanel({
  sessionId,
  tenantId,
  version,
  canWrite,
  oauthNotice,
}: Props) {
  const { data, isLoading, isError, error } = useIntegrationsStepQuery(sessionId, true)
  const patchMutation = usePatchIntegrationsMutation(sessionId)
  const verifyMutation = useVerifyIntegrationMutation(sessionId)
  const connectMutation = useConnectIntegrationMutation(sessionId)
  const patchRoutingMutation = usePatchExternalRoutingMutation(sessionId)
  const previewRoutingMutation = usePreviewExternalRoutingMutation(sessionId)
  const resetRoutingMutation = useResetExternalRoutingMutation(sessionId)
  const unrequestMutation = useUnrequestIntegrationMutation(sessionId)
  const unlinkMutation = useLocalUnlinkIntegrationMutation(sessionId)

  const [gmailSlug, setGmailSlug] = useState("")
  const [boardId, setBoardId] = useState("")
  const [boardName, setBoardName] = useState("")
  const [spreadsheetId, setSpreadsheetId] = useState("")
  const [unlinkOpen, setUnlinkOpen] = useState(false)
  const [unlinkError, setUnlinkError] = useState<string | undefined>()

  useEffect(() => {
    if (!data?.draft) return
    const draft = data.draft as {
      gmail?: { label_scope_slug?: string }
      google_sheets?: { spreadsheet_id?: string }
    }
    setGmailSlug(draft.gmail?.label_scope_slug ?? "")
    setSpreadsheetId(draft.google_sheets?.spreadsheet_id ?? "")
  }, [data])

  if (isLoading) return <LoadingState label="Laddar integrationer…" rows={3} />
  if (isError || !data) {
    return (
      <ErrorState
        title="Kunde inte ladda integrationer"
        description="Integrationssteget kunde inte hämtas."
        technicalDetails={error instanceof Error ? error.message : String(error)}
      />
    )
  }

  const redirectTarget = `/ops/customers/${tenantId}/onboarding`
  const vismaItem = data.integrations.find((i) => i.integration_key === "visma")

  return (
    <div className="min-w-0 space-y-4">
      <h2 className="text-section-title text-text-primary">Integrationer</h2>
      {oauthNotice ? (
        <p className="rounded-md border border-border bg-surface-subtle p-3 text-body-small text-text-secondary">
          {oauthNotice}
        </p>
      ) : null}
      <div className="space-y-3">
        {data.integrations.map((item) => (
          <div
            key={item.integration_key}
            className="min-w-0 rounded-lg border border-border bg-surface-subtle p-4"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-text-primary">{item.label}</span>
              <StatusBadge variant={lifecycleVariant(item.lifecycle_status)} label={item.lifecycle_status} />
              {item.connection_status ? (
                <StatusBadge variant="unknown" label={`connection: ${item.connection_status}`} />
              ) : null}
              {item.verified ? (
                <StatusBadge variant="healthy" label="verified" />
              ) : (
                <StatusBadge variant="warning" label="ej verifierad" />
              )}
            </div>
            <IntegrationMeta item={item} />
            <div className="mt-3 flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={!canWrite || verifyMutation.isPending}
                onClick={() =>
                  void verifyMutation.mutateAsync({
                    integrationKey: item.integration_key,
                    version,
                  })
                }
              >
                Verifiera
              </Button>
              {item.integration_key === "visma" || item.integration_key === "gmail" ? (
                <>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={!canWrite || connectMutation.isPending}
                    onClick={() =>
                      void connectMutation
                        .mutateAsync({
                          integrationKey: item.integration_key,
                          version,
                          redirect_target: redirectTarget,
                        })
                        .then((result) => {
                          window.location.href = result.authorization_url
                        })
                    }
                  >
                    {item.integration_key === "gmail"
                      ? item.connected
                        ? "Återanslut Google"
                        : "Anslut Google"
                      : item.connected
                        ? "Återanslut Visma"
                        : "Anslut Visma"}
                  </Button>
                  {item.integration_key === "visma" && item.connected ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={!canWrite}
                      onClick={() => {
                        setUnlinkError(undefined)
                        setUnlinkOpen(true)
                      }}
                    >
                      Lokalt koppla bort
                    </Button>
                  ) : null}
                </>
              ) : null}
              {item.requested && !item.required ? (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={!canWrite || unrequestMutation.isPending}
                  onClick={() =>
                    void unrequestMutation.mutateAsync({
                      integrationKey: item.integration_key,
                      version,
                    })
                  }
                >
                  Ta bort begäran
                </Button>
              ) : null}
            </div>
            {item.integration_key === "visma" &&
            item.lifecycle_status === "authorization_required" ? (
              <p className="mt-2 text-body-small text-status-warning">
                Auktorisering krävs — anslut Visma via OAuth innan verifiering.
              </p>
            ) : null}
            {item.integration_key === "gmail" &&
            item.lifecycle_status === "authorization_required" ? (
              <p className="mt-2 text-body-small text-status-warning">
                Auktorisering krävs — anslut Google via OAuth innan verifiering.
              </p>
            ) : null}
          </div>
        ))}
      </div>

      <CriticalActionDialog
        open={unlinkOpen}
        title="Lokalt koppla bort Visma"
        consequence="Detta tar bort den lokala OAuth-kopplingen för denna tenant. Extern revoke hos Visma sker inte automatiskt."
        primaryLabel="Koppla bort lokalt"
        loading={unlinkMutation.isPending}
        error={unlinkError}
        onClose={() => setUnlinkOpen(false)}
        onConfirm={(reason) => {
          void unlinkMutation
            .mutateAsync({ integrationKey: "visma", version, reason })
            .then(() => setUnlinkOpen(false))
            .catch((err: unknown) => {
              setUnlinkError(err instanceof Error ? err.message : "Kunde inte koppla bort.")
            })
        }}
      />

      <div className="min-w-0 space-y-3 rounded-lg border border-border p-4">
        <h3 className="text-body font-medium text-text-primary">Gmail label scope</h3>
        <p className="text-body-small text-text-secondary">
          Sparar endast konfiguration — ingen automatisk verifiering eller scan startas.
        </p>
        <input
          className="min-h-11 w-full min-w-0 rounded-md border border-border bg-page px-3"
          value={gmailSlug}
          disabled={!canWrite}
          onChange={(e) => setGmailSlug(e.target.value)}
          placeholder="tenant-slug"
        />
        <Button
          type="button"
          disabled={!canWrite || patchMutation.isPending}
          onClick={() =>
            void patchMutation.mutateAsync({
              version,
              requested_integrations: ["gmail"],
              gmail: { requested: true, label_scope_slug: gmailSlug },
            })
          }
        >
          Spara Gmail-config
        </Button>
      </div>

      <div className="min-w-0 space-y-3 rounded-lg border border-border p-4">
        <h3 className="text-body font-medium text-text-primary">Monday extern routing (lead)</h3>
        <input
          className="min-h-11 w-full min-w-0 rounded-md border border-border bg-page px-3"
          value={boardId}
          disabled={!canWrite}
          onChange={(e) => setBoardId(e.target.value)}
          placeholder="board_id"
        />
        <input
          className="min-h-11 w-full min-w-0 rounded-md border border-border bg-page px-3"
          value={boardName}
          disabled={!canWrite}
          onChange={(e) => setBoardName(e.target.value)}
          placeholder="board_name"
        />
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            disabled={!canWrite || patchRoutingMutation.isPending}
            onClick={() =>
              void patchRoutingMutation.mutateAsync({
                version,
                targets: {
                  lead: {
                    target_type: "monday_board",
                    board_id: boardId,
                    board_name: boardName,
                  },
                },
              })
            }
          >
            Spara extern routing
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={previewRoutingMutation.isPending}
            onClick={() => void previewRoutingMutation.mutateAsync()}
          >
            Förhandsgranska
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={!canWrite || resetRoutingMutation.isPending}
            onClick={() =>
              void resetRoutingMutation.mutateAsync({
                version,
                job_types: ["lead"],
              })
            }
          >
            Återställ till inherit/default
          </Button>
        </div>
        {previewRoutingMutation.data ? (
          <pre className="overflow-x-auto rounded-md bg-page p-3 text-body-small">
            {JSON.stringify(previewRoutingMutation.data.preview, null, 2)}
          </pre>
        ) : null}
        <p className="text-body-small text-text-secondary">
          Ogiltig canonical target → manual_review fallback vid runtime.
        </p>
      </div>

      <div className="min-w-0 space-y-3 rounded-lg border border-border p-4">
        <h3 className="text-body font-medium text-text-primary">Google Sheets</h3>
        <input
          className="min-h-11 w-full min-w-0 rounded-md border border-border bg-page px-3"
          value={spreadsheetId}
          disabled={!canWrite}
          onChange={(e) => setSpreadsheetId(e.target.value)}
          placeholder="spreadsheet_id"
        />
        <Button
          type="button"
          disabled={!canWrite || patchMutation.isPending}
          onClick={() =>
            void patchMutation.mutateAsync({
              version,
              requested_integrations: ["google_sheets"],
              google_sheets: {
                requested: true,
                spreadsheet_id: spreadsheetId,
                export_tabs: ["Leads"],
              },
            })
          }
        >
          Spara Sheets-config
        </Button>
      </div>

      {vismaItem ? (
        <p className="text-body-small text-text-secondary">
          Visma: connection och verification är separata steg. Connected ≠ verified.
        </p>
      ) : null}
    </div>
  )
}
