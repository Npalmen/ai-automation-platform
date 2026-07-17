import { cn } from "@/lib/utils"

type LoadingStateProps = {
  label?: string
  rows?: number
  className?: string
}

export function LoadingState({
  label = "Laddar…",
  rows = 3,
  className,
}: LoadingStateProps) {
  return (
    <div
      className={cn("min-w-0 space-y-3", className)}
      aria-busy="true"
      aria-label={label}
    >
      <p className="sr-only">{label}</p>
      {Array.from({ length: rows }).map((_, index) => (
        <div
          key={index}
          className="h-16 w-full animate-pulse rounded-lg bg-surface-subtle"
        />
      ))}
    </div>
  )
}
