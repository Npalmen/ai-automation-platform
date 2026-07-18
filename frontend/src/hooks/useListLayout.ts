import { useCallback, useEffect, useRef, useState } from "react"

export type ListLayout = "full" | "compact" | "cards"

const FULL_MIN_WIDTH = 1200
const COMPACT_MIN_WIDTH = 768

function layoutForWidth(width: number): ListLayout {
  if (width >= FULL_MIN_WIDTH) {
    return "full"
  }
  if (width >= COMPACT_MIN_WIDTH) {
    return "compact"
  }
  return "cards"
}

/**
 * Measures available content width and returns a stable list layout tier.
 * Starts conservatively at `compact` to avoid full→cards flash with sidebar.
 */
export function useListLayout(): {
  ref: (node: HTMLDivElement | null) => void
  layout: ListLayout
} {
  const [layout, setLayout] = useState<ListLayout>("compact")
  const observerRef = useRef<ResizeObserver | null>(null)
  const elementRef = useRef<HTMLDivElement | null>(null)

  const updateLayout = useCallback((width: number) => {
    const next = layoutForWidth(width)
    setLayout((prev) => (prev === next ? prev : next))
  }, [])

  const ref = useCallback(
    (node: HTMLDivElement | null) => {
      if (observerRef.current) {
        observerRef.current.disconnect()
        observerRef.current = null
      }

      elementRef.current = node

      if (!node || typeof ResizeObserver === "undefined") {
        return
      }

      observerRef.current = new ResizeObserver((entries) => {
        const entry = entries[0]
        if (!entry) {
          return
        }
        updateLayout(entry.contentRect.width)
      })

      observerRef.current.observe(node)
      updateLayout(node.getBoundingClientRect().width)
    },
    [updateLayout],
  )

  useEffect(() => {
    return () => {
      observerRef.current?.disconnect()
      observerRef.current = null
    }
  }, [])

  return { ref, layout }
}
