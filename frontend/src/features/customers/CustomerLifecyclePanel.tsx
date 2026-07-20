import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { CriticalActionDialog } from "@/components/operator/CriticalActionDialog"
import { useAuth } from "@/features/auth/AuthProvider"

import {
  archiveTenant,
  createInvitation,
  deleteTestTenant,
  fetchActivationHistory,
  fetchInvitations,
  fetchLifecycle,
  restoreTenant,
  revokeInvitation,
  type LifecycleInfo,
} from "./lifecycleApi"

const INVITE_STATUS_SV: Record<string, string> = {
  pending: "Inbjudan skickad",
  consumed: "Konto anslutet",
  revoked: "Återkallad",
  expired: "Utgången",
}

type Props = {
  tenantId: string
  initialLifecycle?: LifecycleInfo | null
}

export function CustomerLifecyclePanel({ tenantId, initialLifecycle }: Props) {
  const { auth } = useAuth()
  const qc = useQueryClient()
  const role = auth.status === "authenticated" ? auth.operator.role : null
  const canAdmin = role === "admin" || role === "super_admin"
  const isSuperAdmin = role === "super_admin"

  const lifecycleQuery = useQuery({
    queryKey: ["tenant-lifecycle", tenantId],
    queryFn: () => fetchLifecycle(tenantId),
    initialData: initialLifecycle ?? undefined,
  })
  const historyQuery = useQuery({
    queryKey: ["tenant-activation-history", tenantId],
    queryFn: () => fetchActivationHistory(tenantId),
  })
  const invitesQuery = useQuery({
    queryKey: ["tenant-invitations", tenantId],
    queryFn: () => fetchInvitations(tenantId),
  })

  const [archiveOpen, setArchiveOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [confirmId, setConfirmId] = useState("")
  const [inviteEmail, setInviteEmail] = useState("")

  const lifecycle = lifecycleQuery.data
  const archiveMutation = useMutation({
    mutationFn: () =>
      archiveTenant(tenantId, lifecycle?.config_version ?? 1, "Arkiverad från kundkort"),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["tenant-lifecycle", tenantId] })
      setArchiveOpen(false)
    },
  })
  const restoreMutation = useMutation({
    mutationFn: () =>
      restoreTenant(tenantId, lifecycle?.config_version ?? 1, "Återställd från kundkort"),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["tenant-lifecycle", tenantId] }),
  })
  const inviteMutation = useMutation({
    mutationFn: () =>
      createInvitation(tenantId, {
        integration_key: "gmail",
        contact_email: inviteEmail.trim(),
      }),
    onSuccess: () => {
      setInviteEmail("")
      void qc.invalidateQueries({ queryKey: ["tenant-invitations", tenantId] })
    },
  })
  const revokeMutation = useMutation({
    mutationFn: (id: string) => revokeInvitation(tenantId, id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["tenant-invitations", tenantId] }),
  })
  const deleteMutation = useMutation({
    mutationFn: () =>
      deleteTestTenant(tenantId, {
        confirm_tenant_id: confirmId,
        reason: "Testtenant raderad från kundkort",
      }),
    onSuccess: () => {
      window.location.href = "/customers"
    },
  })

  if (!lifecycle) return null

  return (
    <section className="min-w-0 rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-section-title text-text-primary">Livscykel och åtgärder</h2>
      <dl className="grid gap-2 text-body sm:grid-cols-2">
        <div>
          <dt className="text-caption text-text-secondary">Status</dt>
          <dd className="text-text-primary">{lifecycle.lifecycle_label_sv}</dd>
        </div>
        <div>
          <dt className="text-caption text-text-secondary">Config-version</dt>
          <dd className="text-text-primary">{lifecycle.config_version}</dd>
        </div>
        <div>
          <dt className="text-caption text-text-secondary">Driftpaus</dt>
          <dd className="text-text-primary">
            {lifecycle.operations_paused ? "Pausad" : "Ej pausad"} · Scheduler:{" "}
            {lifecycle.scheduler_run_mode ?? "—"}
          </dd>
        </div>
        <div>
          <dt className="text-caption text-text-secondary">Senast ändrad av</dt>
          <dd className="text-text-primary">
            {lifecycle.last_config_updated_by ?? lifecycle.lifecycle_updated_by ?? "—"}
          </dd>
        </div>
      </dl>

      <div className="mt-4 flex flex-wrap gap-2">
        {canAdmin && lifecycle.lifecycle_status !== "archived" ? (
          <Button variant="outline" onClick={() => setArchiveOpen(true)}>
            Arkivera
          </Button>
        ) : null}
        {canAdmin && lifecycle.lifecycle_status === "archived" ? (
          <Button
            variant="outline"
            onClick={() => void restoreMutation.mutate()}
            disabled={restoreMutation.isPending}
          >
            Återställ
          </Button>
        ) : null}
        {isSuperAdmin && lifecycle.is_test_tenant ? (
          <Button variant="outline" onClick={() => setDeleteOpen(true)}>
            Radera testkund
          </Button>
        ) : null}
      </div>

      <div className="mt-6 space-y-2">
        <h3 className="text-label text-text-primary">Kundinbjudan (Gmail)</h3>
        <div className="flex flex-wrap gap-2">
          <input
            className="min-h-11 min-w-0 flex-1 rounded-md border border-border bg-page px-3 text-body"
            placeholder="kund@foretag.se"
            value={inviteEmail}
            onChange={(e) => setInviteEmail(e.target.value)}
          />
          <Button
            disabled={!inviteEmail.trim() || inviteMutation.isPending}
            onClick={() => void inviteMutation.mutate()}
          >
            Skapa inbjudan
          </Button>
        </div>
        <ul className="space-y-1 text-body-small text-text-secondary">
          {(invitesQuery.data ?? []).map((inv) => (
            <li key={inv.id} className="flex flex-wrap items-center gap-2">
              <span>
                {inv.contact_email} — {INVITE_STATUS_SV[inv.status] ?? inv.status}
                {inv.connected_account_email ? ` (${inv.connected_account_email})` : ""}
              </span>
              {inv.status === "pending" ? (
                <Button size="sm" variant="outline" onClick={() => void revokeMutation.mutate(inv.id)}>
                  Återkalla
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-6">
        <h3 className="text-label text-text-primary">Aktiveringshistorik</h3>
        <ul className="mt-2 space-y-1 text-body-small text-text-secondary">
          {(historyQuery.data?.items ?? []).slice(0, 5).map((item) => (
            <li key={item.id}>
              v{item.config_version} · {new Date(item.activated_at).toLocaleString("sv-SE")} ·{" "}
              {item.activated_by_operator_id}
            </li>
          ))}
          {!historyQuery.data?.items?.length ? <li>Ingen aktiveringshistorik ännu.</li> : null}
        </ul>
      </div>

      <CriticalActionDialog
        open={archiveOpen}
        title="Arkivera kund"
        consequence="Arkiverade kunder kan inte scannas eller köra automation."
        primaryLabel="Arkivera"
        loading={archiveMutation.isPending}
        onClose={() => setArchiveOpen(false)}
        onConfirm={() => void archiveMutation.mutateAsync()}
      />
      <CriticalActionDialog
        open={deleteOpen}
        title="Radera testkund permanent"
        consequence={`Skriv tenant-ID (${tenantId}) i bekräftelsefältet nedan innan du fortsätter.`}
        primaryLabel="Radera"
        loading={deleteMutation.isPending}
        onClose={() => {
          setDeleteOpen(false)
          setConfirmId("")
        }}
        onConfirm={() => {
          if (confirmId !== tenantId) return
          void deleteMutation.mutateAsync()
        }}
      />
      {deleteOpen ? (
        <div className="mt-2">
          <label className="block text-body-small text-text-secondary">
            Bekräfta tenant-ID
            <input
              className="mt-1 w-full rounded-md border border-border bg-page px-3 py-2 text-body"
              value={confirmId}
              onChange={(e) => setConfirmId(e.target.value)}
              placeholder={tenantId}
            />
          </label>
        </div>
      ) : null}
    </section>
  )
}
