import { useEffect } from "react"
import { useBlocker } from "react-router-dom"

type Props = {
  when: boolean
  onBlock?: () => void
}

export function UnsavedChangesGuard({ when, onBlock }: Props) {
  const blocker = useBlocker(when)

  useEffect(() => {
    if (!when) return
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ""
    }
    window.addEventListener("beforeunload", handler)
    return () => window.removeEventListener("beforeunload", handler)
  }, [when])

  useEffect(() => {
    if (blocker.state === "blocked") {
      onBlock?.()
      const proceed = window.confirm(
        "Du har osparade ändringar. Vill du lämna sidan utan att spara?",
      )
      if (proceed) {
        blocker.proceed()
      } else {
        blocker.reset()
      }
    }
  }, [blocker, onBlock])

  return null
}
