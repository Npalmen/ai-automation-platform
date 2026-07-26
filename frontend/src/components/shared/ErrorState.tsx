import { cn } from "@/lib/utils"

type ErrorStateProps = {
  title: string
  description: string
  className?: string
}

export function ErrorState({
  title,
  description,
  className,
}: ErrorStateProps) {
  return (
    <div
      className={cn(
        "flex min-w-0 flex-col gap-3 rounded-lg border border-status-danger/30 bg-status-danger/5 p-4",
        className,
      )}
      role="alert"
    >
      <h2 className="text-section-title text-text-primary">{title}</h2>
      <p className="break-words text-body text-text-secondary">{description}</p>
    </div>
  )
}
