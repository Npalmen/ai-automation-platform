import { useState } from "react"

import {
  formatIncidentError,
  useAddIncidentNoteMutation,
} from "../mutations"
import type { IncidentDetail } from "../types"

type IncidentNoteFormProps = {
  incident: IncidentDetail
  disabled?: boolean
}

export function IncidentNoteForm({ incident, disabled }: IncidentNoteFormProps) {
  const [message, setMessage] = useState("")
  const mutation = useAddIncidentNoteMutation(incident.incident_id)

  return (
    <form
      className="flex min-w-0 flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault()
        if (!message.trim()) return
        mutation.mutate(
          { message: message.trim(), confirmation: true },
          { onSuccess: () => setMessage("") },
        )
      }}
    >
      <label className="flex flex-col gap-1">
        <span className="text-label text-text-muted">Intern anteckning</span>
        <textarea
          className="min-h-24 w-full rounded-md border border-border bg-page px-3 text-body text-text-primary disabled:opacity-50"
          value={message}
          disabled={disabled || mutation.isPending}
          onChange={(e) => setMessage(e.target.value)}
        />
      </label>
      {mutation.isError && (
        <p className="text-body-small text-status-danger">
          {formatIncidentError(mutation.error)}
        </p>
      )}
      <button
        type="submit"
        className="self-start rounded-md border border-border bg-surface px-3 py-2 text-body text-text-primary disabled:opacity-50"
        disabled={disabled || mutation.isPending || !message.trim()}
      >
        Lägg till anteckning
      </button>
    </form>
  )
}
