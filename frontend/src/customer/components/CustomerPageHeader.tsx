type CustomerPageHeaderProps = {
  title: string
  description?: string
}

export function CustomerPageHeader({
  title,
  description,
}: CustomerPageHeaderProps) {
  return (
    <header className="mb-6 min-w-0">
      <h1
        className="text-page-title text-text-primary"
        tabIndex={-1}
      >
        {title}
      </h1>
      {description ? (
        <p className="mt-2 max-w-3xl text-body text-text-secondary">
          {description}
        </p>
      ) : null}
    </header>
  )
}
