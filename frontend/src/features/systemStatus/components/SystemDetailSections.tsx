import type { SystemStatusResponse } from "../types"
import { formatBuildTime, formatDeployTime, formatTimestamp, verificationLabel } from "../formatters"
import { StatusCardList } from "./StatusSections"

type ResilienceSectionProps = {
  resilience: SystemStatusResponse["resilience"]
  generatedAt: string
}

export function ResilienceSection({ resilience, generatedAt }: ResilienceSectionProps) {
  return (
    <section aria-labelledby="system-resilience-heading" className="flex min-w-0 flex-col gap-4">
      <h2 id="system-resilience-heading" className="text-section-title text-text-primary">
        Resiliens (backup och restore)
      </h2>
      <StatusCardList
        generatedAt={generatedAt}
        items={[
          { key: "backup", component: resilience.last_backup },
          { key: "restore", component: resilience.last_restore_test },
          { key: "retention", component: resilience.retention },
        ]}
      />
      <div className="grid min-w-0 gap-3 text-body-small text-text-secondary sm:grid-cols-2">
        <p>
          Backup:{" "}
          {resilience.last_backup.details?.completed_at
            ? formatTimestamp(String(resilience.last_backup.details.completed_at))
            : "—"}
        </p>
        <p>
          Arkivintegritet:{" "}
          {resilience.last_backup.archive_integrity_verified === true
            ? "Verifierad (gunzip -t)"
            : resilience.last_backup.archive_integrity_verified === false
              ? "Ej verifierad"
              : "—"}
        </p>
        <p>
          Restore-test:{" "}
          {resilience.last_restore_test.details?.completed_at
            ? formatTimestamp(String(resilience.last_restore_test.details.completed_at))
            : "—"}
        </p>
        <p>
          Schemavalidering: {verificationLabel(resilience.last_restore_test.schema_verification)}
        </p>
      </div>
    </section>
  )
}

type DeployReadinessSectionProps = {
  deployment: SystemStatusResponse["deployment"]
  generatedAt: string
}

export function DeployReadinessSection({
  deployment,
  generatedAt,
}: DeployReadinessSectionProps) {
  return (
    <section
      aria-labelledby="system-deploy-heading"
      className="flex min-w-0 flex-col gap-4"
    >
      <h2 id="system-deploy-heading" className="text-section-title text-text-primary">
        Deploy readiness
      </h2>
      <p className="text-body-small text-text-secondary">
        Deploy readiness påverkar inte runtime-status automatiskt.
      </p>
      <StatusCardList
        generatedAt={generatedAt}
        items={[
          { key: "build", component: deployment.current_build },
          { key: "deploy", component: deployment.last_deploy },
          { key: "routing", component: deployment.routing_config },
          { key: "gate", component: deployment.release_gate },
        ]}
      />
      <div className="grid min-w-0 gap-3 text-body-small text-text-secondary sm:grid-cols-2">
        <p>Build-ID: {deployment.current_build.commit_sha ?? "—"}</p>
        <p>Byggtid: {formatBuildTime(deployment.current_build.build_time)}</p>
        <p>Release: {deployment.current_build.release_id ?? "—"}</p>
        <p>Deploytid: {formatDeployTime(deployment.last_deploy.deployed_at)}</p>
      </div>
    </section>
  )
}

type LimitationsNoteProps = {
  limitations: string[]
}

export function LimitationsNote({ limitations }: LimitationsNoteProps) {
  if (limitations.length === 0) return null
  return (
    <aside className="rounded-lg border border-border bg-surface-subtle p-4">
      <h2 className="mb-2 text-card-title text-text-primary">Begränsningar</h2>
      <ul className="list-disc space-y-1 pl-5 text-body-small text-text-secondary">
        {limitations.map((item) => (
          <li key={item} className="break-words">
            {item}
          </li>
        ))}
      </ul>
    </aside>
  )
}

type RunbookLinksProps = {
  runbooks: SystemStatusResponse["runbooks"]
}

export function RunbookLinks({ runbooks }: RunbookLinksProps) {
  if (runbooks.length === 0) return null
  return (
    <section aria-labelledby="system-runbooks-heading">
      <h2 id="system-runbooks-heading" className="mb-2 text-section-title text-text-primary">
        Runbooks
      </h2>
      <ul className="flex min-w-0 flex-wrap gap-2">
        {runbooks.map((book) => (
          <li
            key={book.id}
            className="rounded-md border border-border bg-surface px-3 py-1.5 text-label text-text-secondary"
          >
            {book.label}
          </li>
        ))}
      </ul>
    </section>
  )
}
