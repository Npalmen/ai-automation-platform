import { PageHeader } from "@/components/operator/PageHeader"

export function ForbiddenPage() {
  return (
    <div className="min-h-screen bg-page px-4 py-8 sm:px-6">
      <div className="mx-auto w-full max-w-lg">
        <PageHeader
          title="Åtkomst nekad"
          description="Din roll har inte behörighet att öppna den här sidan. Kontakta en administratör om du behöver utökad åtkomst."
        />
      </div>
    </div>
  )
}
