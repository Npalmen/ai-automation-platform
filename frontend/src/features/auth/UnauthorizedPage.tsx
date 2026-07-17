import { PageHeader } from "@/components/operator/PageHeader"

export function UnauthorizedPage() {
  return (
    <div className="min-h-screen bg-page px-4 py-8 sm:px-6">
      <div className="mx-auto w-full max-w-lg">
        <PageHeader
          title="Sessionen saknas"
          description="Din operatörssession har gått ut eller är inte giltig. Logga in igen för att fortsätta."
        />
      </div>
    </div>
  )
}
