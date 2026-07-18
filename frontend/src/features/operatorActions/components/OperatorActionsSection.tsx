import { useMemo, useState } from "react"
import type { UseMutationResult } from "@tanstack/react-query"

import {
  usePauseAutomationMutation,
  usePauseSchedulerMutation,
  useRejectApprovalMutation,
  useApproveApprovalMutation,
  useResumeAutomationMutation,
  useResumeSchedulerMutation,
} from "../mutations"
import type {
  AvailableActionMeta,
  OperatorActionRequest,
  OperatorActionResponse,
} from "../types"
import { OperatorActionButton, OperatorActionDialog } from "./OperatorActionDialog"

type OperatorActionsSectionProps = {
  title?: string
  tenantId: string
  tenantLabel: string
  actions: AvailableActionMeta[]
  approvalId?: string
}

type ActiveMutation = UseMutationResult<
  OperatorActionResponse,
  unknown,
  Omit<OperatorActionRequest, "idempotency_key">,
  unknown
>

function useActionMutation(
  actionId: string,
  tenantId: string,
  approvalId?: string,
): ActiveMutation | null {
  const pauseAutomation = usePauseAutomationMutation(tenantId)
  const resumeAutomation = useResumeAutomationMutation(tenantId)
  const pauseScheduler = usePauseSchedulerMutation(tenantId)
  const resumeScheduler = useResumeSchedulerMutation(tenantId)
  const rejectApproval = useRejectApprovalMutation(tenantId, approvalId ?? "")
  const approveApproval = useApproveApprovalMutation(tenantId, approvalId ?? "")

  return useMemo(() => {
    switch (actionId) {
      case "tenant.pause_automation":
        return pauseAutomation
      case "tenant.resume_automation":
        return resumeAutomation
      case "tenant.scheduler.pause":
        return pauseScheduler
      case "tenant.scheduler.resume":
        return resumeScheduler
      case "approval.reject":
        return approvalId ? rejectApproval : null
      case "approval.approve":
        return approvalId ? approveApproval : null
      default:
        return null
    }
  }, [
    actionId,
    approvalId,
    pauseAutomation,
    pauseScheduler,
    rejectApproval,
    approveApproval,
    resumeAutomation,
    resumeScheduler,
  ])
}

export function OperatorActionsSection({
  title = "Operatörsåtgärder",
  tenantId,
  tenantLabel,
  actions,
  approvalId,
}: OperatorActionsSectionProps) {
  const [activeAction, setActiveAction] = useState<AvailableActionMeta | null>(null)
  const activeMutation = useActionMutation(
    activeAction?.action_id ?? "",
    tenantId,
    approvalId,
  )

  if (actions.length === 0) {
    return null
  }

  return (
    <section className="min-w-0 rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-section-title text-text-primary">{title}</h2>
      <p className="mb-4 text-body-small text-text-secondary">
        Säkra driftåtgärder med obligatorisk anledning och bekräftelse. Tillgänglighet
        styrs av backend utifrån aktuellt läge och din roll.
      </p>
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:flex-wrap">
        {actions.map((action) => (
          <OperatorActionButton
            key={action.action_id}
            action={action}
            onClick={() => setActiveAction(action)}
          />
        ))}
      </div>
      {!actions.some((action) => action.allowed) ? (
        <p className="mt-3 text-body-small text-text-muted">
          Du saknar behörighet att utföra tillgängliga åtgärder.
        </p>
      ) : null}
      {activeAction && activeMutation ? (
        <OperatorActionDialog
          open
          action={activeAction}
          tenantLabel={tenantLabel}
          mutation={activeMutation}
          onClose={() => setActiveAction(null)}
        />
      ) : null}
    </section>
  )
}

export function parseApprovalIdFromItemId(itemId: string): string | undefined {
  if (!itemId.startsWith("approval:")) {
    return undefined
  }
  const approvalId = itemId.slice("approval:".length).trim()
  return approvalId || undefined
}
