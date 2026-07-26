import { useEffect } from "react"
import { useLocation } from "react-router-dom"

/**
 * Moves focus to the page heading after route changes so keyboard users
 * land on relevant content. Query-only updates are intentionally ignored.
 */
export function useRouteFocus() {
  const { pathname } = useLocation()

  useEffect(() => {
    const main = document.getElementById("main-content")
    if (!main) return

    const heading = main.querySelector("h1")
    const focusTarget =
      heading instanceof HTMLElement ? heading : main

    focusTarget.focus({ preventScroll: false })
  }, [pathname])
}
