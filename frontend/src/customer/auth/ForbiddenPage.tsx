import { Link } from "react-router-dom"

import { CustomerPageContainer } from "@/customer/components/CustomerPageContainer"
import { CustomerPageHeader } from "@/customer/components/CustomerPageHeader"
import { ErrorState } from "@/components/shared/ErrorState"

export function ForbiddenPage() {
  return (
    <CustomerPageContainer>
      <CustomerPageHeader
        title="Åtkomst nekad"
        description="Du har inte behörighet att visa den här sidan."
      />
      <ErrorState
        title="Behörighet saknas"
        description="Kontakta din administratör om du tror att detta är fel."
      />
      <p className="mt-4">
        <Link
          to="/"
          className="text-body text-brand underline-offset-2 hover:underline"
        >
          Tillbaka till översikten
        </Link>
      </p>
    </CustomerPageContainer>
  )
}
