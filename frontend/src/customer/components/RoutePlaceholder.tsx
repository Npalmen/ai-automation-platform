import { WorkspaceModeBadge } from "@/customer/components/WorkspaceModeBadge"
import { CustomerPageContainer } from "@/customer/components/CustomerPageContainer"
import { CustomerPageHeader } from "@/customer/components/CustomerPageHeader"
import { EmptyState } from "@/components/shared/EmptyState"

type RoutePlaceholderProps = {
  title: string
  description: string
}

export function RoutePlaceholder({ title, description }: RoutePlaceholderProps) {
  return (
    <CustomerPageContainer>
      <CustomerPageHeader title={title} description={description} />
      <div className="mb-4">
        <WorkspaceModeBadge />
      </div>
      <EmptyState
        title="Kommer snart"
        description="Den här vyn ingår i arbetsytan och visas här när funktionen är klar. Just nu körs förhandsvisning med exempeldata — inga riktiga ärenden visas."
      />
    </CustomerPageContainer>
  )
}
