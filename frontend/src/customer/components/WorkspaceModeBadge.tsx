import { useCustomerAuth } from "@/customer/auth/CustomerAuthProvider"
import { cn } from "@/lib/utils"

export function WorkspaceModeBadge({ className }: { className?: string }) {
  const { auth } = useCustomerAuth()
  const label =
    auth.mode === "preview"
      ? "Förhandsvisning"
      : auth.mode === "mock"
        ? "Exempelläge"
        : "Arbetsyta"

  return (
    <span
      role="status"
      className={cn(
        "inline-flex items-center rounded-full border border-status-information/40 bg-status-information/10 px-3 py-1 text-caption font-medium text-text-secondary",
        className,
      )}
    >
      {label}
      {auth.connected ? null : " · ej ansluten"}
    </span>
  )
}
