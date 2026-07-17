type DataQualityNoteProps = {
  notes: string[]
}

export function DataQualityNote({ notes }: DataQualityNoteProps) {
  if (notes.length === 0) return null

  return (
    <section aria-labelledby="usage-data-quality-heading" className="rounded-lg border border-border bg-surface-subtle p-4">
      <h2 id="usage-data-quality-heading" className="mb-2 text-section-title text-text-primary">
        Datakvalitet
      </h2>
      <ul className="list-disc space-y-1 pl-5 text-body-small text-text-secondary">
        {notes.map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>
    </section>
  )
}
