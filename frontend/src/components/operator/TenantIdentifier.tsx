import { cn } from "@/lib/utils"

type TenantIdentifierProps = {
  tenantId: string
  className?: string
}

export function TenantIdentifier({ tenantId, className }: TenantIdentifierProps) {
  return (
    <code
      className={cn(
        "block max-w-full truncate font-mono text-body-small text-text-secondary break-all sm:break-normal",
        className,
      )}
      title={tenantId}
    >
      {tenantId}
    </code>
  )
}
