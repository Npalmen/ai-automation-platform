import { Link } from "react-router-dom"

import { CustomerPageContainer } from "@/customer/components/CustomerPageContainer"
import { CustomerPageHeader } from "@/customer/components/CustomerPageHeader"
import { WorkspaceModeBadge } from "@/customer/components/WorkspaceModeBadge"

export function PreviewLoginPage() {
  return (
    <CustomerPageContainer>
      <CustomerPageHeader
        title="Förhandsvisning"
        description="Kundens arbetsyta körs i förhandsläge med exempeldata. Ansluten inloggning är inte tillgänglig ännu."
      />
      <div className="rounded-lg border border-border bg-surface p-6">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <WorkspaceModeBadge />
        </div>
        <p className="text-body text-text-secondary">
          När ansluten inloggning finns kommer du kunna logga in säkert utan
          att lagra känsliga uppgifter i webbläsaren. Tills dess visar
          arbetsytan hur navigation och vyer kommer att fungera.
        </p>
        <p className="mt-4">
          <Link
            to="/"
            className="inline-flex min-h-11 items-center rounded-md bg-brand px-4 text-body font-medium text-brand-foreground hover:bg-brand/90"
          >
            Till arbetsytan
          </Link>
        </p>
      </div>
    </CustomerPageContainer>
  )
}
