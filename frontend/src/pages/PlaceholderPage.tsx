import { PageHeader } from "@/components/operator/PageHeader"

type PlaceholderPageProps = {
  title: string
  description: string
}

export function PlaceholderPage({ title, description }: PlaceholderPageProps) {
  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      <PageHeader title={title} description={description} />
      <p className="text-body text-text-secondary">
        Funktionen byggs i ett senare kapitel.
      </p>
    </div>
  )
}
