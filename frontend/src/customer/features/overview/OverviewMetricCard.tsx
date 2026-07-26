type OverviewMetricCardProps = {
  label: string
  value: string
}

export function OverviewMetricCard({ label, value }: OverviewMetricCardProps) {
  return (
    <article className="rounded-lg border border-border bg-surface p-4">
      <p className="text-body-small text-text-secondary">{label}</p>
      <p className="mt-2 text-2xl font-semibold tabular-nums text-text-primary">
        {value}
      </p>
    </article>
  )
}
