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
import type {
  IntegrationLifecycleItem,
  IntegrationSelectionDraft,
  IntegrationSelectionStatus,
} from "./types"
import { CriticalActionDialog } from "@/components/operator/CriticalActionDialog"
import { ErrorState } from "@/components/operator/ErrorState"
import { LoadingState } from "@/components/operator/LoadingState"
import { StatusBadge } from "@/components/operator/StatusBadge"
import { Button } from "@/components/ui/button"
import { useEffect, useMemo, useState } from "react"

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
  metadata_read_failed: "Kunde inte läsa kalkylarkets metadata.",
  label_invalid: "Ogiltig Gmail-label.",
}

const CATEGORY_ORDER = [
  "email",
  "finance",
  "work_management",
  "spreadsheet_export",
  "calendar",
] as const

const CATEGORY_LABELS: Record<string, string> = {
  email: "E-post",
  finance: "Ekonomi",
  work_management: "Arbetsledning",
  spreadsheet_export: "Kalkylark/export",
  calendar: "Kalender",
  other: "Övrigt",
}

const SELECTION_LABELS: Record<IntegrationSelectionStatus, string> = {
  not_selected: "Ej aktuell",
  selected_optional: "Valfri",
  selected_required: "Obligatorisk",
}

function lifecycleVariant(status: string): "healthy" | "warning" | "critical" | "unknown" {
  if (status === "verified" || status === "configured_not_running") return "healthy"
  if (status === "authorization_required" || status === "connected") return "warning"
  if (status === "blocked") return "critical"
  return "unknown"
}

function selectionKeyForItem(item: IntegrationLifecycleItem): string {
  return item.canonical_integration_key ?? item.integration_key
}

function isSelected(item: IntegrationLifecycleItem): boolean {
  const status = item.selection_status ?? (item.requested ? "selected_optional" : "not_selected")
  return status === "selected_optional" || status === "selected_required"
}

function groupIntegrations(items: IntegrationLifecycleItem[]) {
  const groups = new Map<string, IntegrationLifecycleItem[]>()
  for (const item of items) {
    const category = item.category ?? "other"
    const bucket = groups.get(category) ?? []
    bucket.push(item)
    groups.set(category, bucket)
  }
  const ordered = [
    ...CATEGORY_ORDER.filter((category) => groups.has(category)),
    ...[...groups.keys()].filter((category) => !CATEGORY_ORDER.includes(category as (typeof CATEGORY_ORDER)[number])),
  ]
  return ordered.map((category) => ({
    category,
    label: CATEGORY_LABELS[category] ?? category,
    items: groups.get(category) ?? [],
  }))
}

function IntegrationMeta({ item }: { item: IntegrationLifecycleItem }) {
  const errorCopy = item.verification_error_code
    ? ERROR_COPY[item.verification_error_code] ?? item.verification_error_code
    : null

  if (!isSelected(item)) {
    return (
      <p className="mt-2 text-body-small text-text-secondary">
        Integrationen är markerad som ej aktuell — anslutning och verifiering visas inte.
      </p>
    )
  }

  return (
    <div className="mt-2 space-y-1 text-body-small text-text-secondary">
      <p>
        Konfigurerad: {item.configured ? "ja" : "nej"} · Ansluten: {item.connected ? "ja" : "nej"} ·
        Verifierad: {item.verified ? "ja" : "nej"}
      </p>
      {item.migration_review_required ? (
        <p className="text-status-warning">Migreringsgranskning krävs innan aktivering.</p>
      ) : null}
      {item.verified_at ? (
        <p>Senast verifierad: {new Date(item.verified_at).toLocaleString("sv-SE")}</p>
      ) : null}
      {item.freshness_max_hours ? <p>Freshness: max {item.freshness_max_hours} timmar</p> : null}
      {errorCopy ? <p className="text-status-warning">Fel: {errorCopy}</p> : null}
      {item.gmail_classification ? (
        <ul className="list-inside list-disc">
          <li>Label/query: {item.gmail_classification.label_query ?? "—"}</li>
          <li>Plattformscredential: {item.gmail_classification.platform_credential}</li>
          <li>Tenant mailbox/label: {item.gmail_classification.tenant_mailbox_access}</li>
          <li>Live intake: {item.gmail_classification.live_intake}</li>
          <li>
            Capability operational: {item.gmail_classification.capability_operational ? "ja" : "nej"}
          </li>
        </ul>
      ) : null}
    </div>
  )
}

type IntegrationCardProps = {
  item: IntegrationLifecycleItem
  canWrite: boolean
  version: number
  redirectTarget: string
  gmailSlug: string
  setGmailSlug: (value: string) => void
  boardId: string
  setBoardId: (value: string) => void
  boardName: string
  setBoardName: (value: string) => void
  spreadsheetId: string
  setSpreadsheetId: (value: string) => void
  onSelectionChange: (canonicalKey: string, selection: IntegrationSelectionDraft) => void
  onUnlinkVisma: () => void
  patchMutationPending: boolean
  verifyMutation: ReturnType<typeof useVerifyIntegrationMutation>
  connectMutation: ReturnType<typeof useConnectIntegrationMutation>
  patchRoutingMutation: ReturnType<typeof usePatchExternalRoutingMutation>
  previewRoutingMutation: ReturnType<typeof usePreviewExternalRoutingMutation>
  resetRoutingMutation: ReturnType<typeof useResetExternalRoutingMutation>
  unrequestMutation: ReturnType<typeof useUnrequestIntegrationMutation>
}

function IntegrationCard({
  item,
  canWrite,
  version,
  redirectTarget,
  gmailSlug,
  setGmailSlug,
  boardId,
  setBoardId,
  boardName,
  setBoardName,
  spreadsheetId,
  setSpreadsheetId,
  onSelectionChange,
  onUnlinkVisma,
  patchMutationPending,
  verifyMutation,
  connectMutation,
  patchRoutingMutation,
  previewRoutingMutation,
  resetRoutingMutation,
  unrequestMutation,
}: IntegrationCardProps) {
  const selectionStatus: IntegrationSelectionStatus =
    item.selection_status ?? (item.requested ? "selected_optional" : "not_selected")
  const comingLater = item.support_status === "coming_later"
  const selectable = item.selectable !== false && !comingLater
  const selected = isSelected(item)
  const showConnection = selected && item.supported_in_current_slice !== false

  return (
    <div className="min-w-0 rounded-lg border border-border bg-surface-subtle p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-text-primary">{item.label}</span>
        {comingLater ? <StatusBadge variant="unknown" label="Kommer senare" /> : null}
        {item.required ? <StatusBadge variant="warning" label="modulkrav" /> : null}
      </div>

      <div className="mt-3 space-y-1">
        <label className="text-body-small font-medium text-text-primary" htmlFor={`selection-${item.integration_key}`}>
          Val för onboarding
        </label>
        <select
          id={`selection-${item.integration_key}`}
          className="min-h-11 w-full max-w-sm rounded-md border border-border bg-page px-3 text-body-small"
          value={selectionStatus}
          disabled={!canWrite || !selectable || patchMutationPending}
          onChange={(event) =>
            onSelectionChange(selectionKeyForItem(item), {
              selection_status: event.target.value as IntegrationSelectionStatus,
              migration_review_required: item.migration_review_required ?? false,
            })
          }
        >
          {(Object.keys(SELECTION_LABELS) as IntegrationSelectionStatus[]).map((status) => (
            <option key={status} value={status}>
              {SELECTION_LABELS[status]}
            </option>
          ))}
        </select>
        <p className="text-body-small text-text-secondary">
          Valet styr om integrationen ska ingå. Anslutning och verifiering är separata steg nedan.
        </p>
      </div>

      {showConnection ? (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-3">
            <span className="text-body-small font-medium text-text-primary">Anslutning</span>
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
                    onClick={onUnlinkVisma}
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
          {item.integration_key === "visma" && item.lifecycle_status === "authorization_required" ? (
            <p className="mt-2 text-body-small text-status-warning">
              Auktorisering krävs — anslut Visma via OAuth innan verifiering.
            </p>
          ) : null}
          {item.integration_key === "gmail" && item.lifecycle_status === "authorization_required" ? (
            <p className="mt-2 text-body-small text-status-warning">
              Auktorisering krävs — anslut Google via OAuth innan verifiering.
            </p>
          ) : null}

          {item.integration_key === "gmail" ? (
            <div className="mt-4 space-y-2 border-t border-border pt-3">
              <h4 className="text-body-small font-medium text-text-primary">Gmail label scope</h4>
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
            </div>
          ) : null}

          {item.integration_key === "monday" ? (
            <div className="mt-4 space-y-2 border-t border-border pt-3">
              <h4 className="text-body-small font-medium text-text-primary">Monday extern routing (lead)</h4>
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
                  size="sm"
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
                  size="sm"
                  variant="outline"
                  disabled={previewRoutingMutation.isPending}
                  onClick={() => void previewRoutingMutation.mutateAsync()}
                >
                  Förhandsgranska
                </Button>
                <Button
                  type="button"
                  size="sm"
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
            </div>
          ) : null}

          {item.integration_key === "google_sheets" ? (
            <div className="mt-4 space-y-2 border-t border-border pt-3">
              <h4 className="text-body-small font-medium text-text-primary">Google Sheets</h4>
              <input
                className="min-h-11 w-full min-w-0 rounded-md border border-border bg-page px-3"
                value={spreadsheetId}
                disabled={!canWrite}
                onChange={(e) => setSpreadsheetId(e.target.value)}
                placeholder="spreadsheet_id"
              />
            </div>
          ) : null}
        </>
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

  const groupedIntegrations = useMemo(
    () => groupIntegrations(data?.integrations ?? []),
    [data?.integrations],
  )

  const handleSelectionChange = (canonicalKey: string, selection: IntegrationSelectionDraft) => {
    void patchMutation.mutateAsync({
      version,
      selections: { [canonicalKey]: selection },
    })
  }

  const saveGmailConfig = () => {
    void patchMutation.mutateAsync({
      version,
      requested_integrations: ["gmail"],
      gmail: { requested: true, label_scope_slug: gmailSlug },
      selections: {
        google_mail: { selection_status: "selected_optional", migration_review_required: false },
      },
    })
  }

  const saveSheetsConfig = () => {
    void patchMutation.mutateAsync({
      version,
      requested_integrations: ["google_sheets"],
      google_sheets: {
        requested: true,
        spreadsheet_id: spreadsheetId,
        export_tabs: ["Leads"],
      },
      selections: {
        google_sheets: { selection_status: "selected_optional", migration_review_required: false },
      },
    })
  }

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
  const gmailItem = data.integrations.find((i) => i.integration_key === "gmail")
  const sheetsItem = data.integrations.find((i) => i.integration_key === "google_sheets")

  return (
    <div className="min-w-0 space-y-4">
      <h2 className="text-section-title text-text-primary">Integrationer</h2>
      <p className="text-body-small text-text-secondary">
        Välj först om varje integration är ej aktuell, valfri eller obligatorisk. Anslutning och
        verifiering görs separat för valda integrationer.
      </p>
      {oauthNotice ? (
        <p className="rounded-md border border-border bg-surface-subtle p-3 text-body-small text-text-secondary">
          {oauthNotice}
        </p>
      ) : null}

      {groupedIntegrations.map((group) => (
        <section key={group.category} className="space-y-3">
          <h3 className="text-body font-medium text-text-primary">{group.label}</h3>
          {group.items.map((item) => (
            <IntegrationCard
              key={item.integration_key}
              item={item}
              canWrite={canWrite}
              version={version}
              redirectTarget={redirectTarget}
              gmailSlug={gmailSlug}
              setGmailSlug={setGmailSlug}
              boardId={boardId}
              setBoardId={setBoardId}
              boardName={boardName}
              setBoardName={setBoardName}
              spreadsheetId={spreadsheetId}
              setSpreadsheetId={setSpreadsheetId}
              onSelectionChange={handleSelectionChange}
              onUnlinkVisma={() => {
                setUnlinkError(undefined)
                setUnlinkOpen(true)
              }}
              patchMutationPending={patchMutation.isPending}
              verifyMutation={verifyMutation}
              connectMutation={connectMutation}
              patchRoutingMutation={patchRoutingMutation}
              previewRoutingMutation={previewRoutingMutation}
              resetRoutingMutation={resetRoutingMutation}
              unrequestMutation={unrequestMutation}
            />
          ))}
        </section>
      ))}

      {gmailItem && isSelected(gmailItem) ? (
        <div className="flex justify-end">
          <Button type="button" disabled={!canWrite || patchMutation.isPending} onClick={saveGmailConfig}>
            Spara Gmail-config
          </Button>
        </div>
      ) : null}
      {sheetsItem && isSelected(sheetsItem) ? (
        <div className="flex justify-end">
          <Button type="button" disabled={!canWrite || patchMutation.isPending} onClick={saveSheetsConfig}>
            Spara Sheets-config
          </Button>
        </div>
      ) : null}

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

      {vismaItem && isSelected(vismaItem) ? (
        <p className="text-body-small text-text-secondary">
          Visma: connection och verification är separata steg. Connected ≠ verified.
        </p>
      ) : null}
    </div>
  )
}
