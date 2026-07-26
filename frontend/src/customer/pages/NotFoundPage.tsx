import { Link } from "react-router-dom"

import { CustomerPageContainer } from "@/customer/components/CustomerPageContainer"
import { CustomerPageHeader } from "@/customer/components/CustomerPageHeader"

export function NotFoundPage() {
  return (
    <CustomerPageContainer>
      <CustomerPageHeader
        title="Sidan hittades inte"
        description="Adressen du försökte öppna finns inte i arbetsytan."
      />
      <p>
        <Link
          to="/"
          className="inline-flex min-h-11 items-center text-body text-brand underline-offset-2 hover:underline"
        >
          Tillbaka till översikten
        </Link>
      </p>
    </CustomerPageContainer>
  )
}
