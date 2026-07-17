export function formatWindow(windowHours: number | null | undefined): string {
  if (windowHours == null) {
    return "Just nu"
  }
  if (windowHours === 24) {
    return "Senaste 24 timmar"
  }
  if (windowHours === 48) {
    return "Senaste 48 timmar"
  }
  return `Senaste ${windowHours} timmar`
}

export function formatGeneratedAt(iso: string): string {
  try {
    return new Intl.DateTimeFormat("sv-SE", {
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(iso))
  } catch {
    return iso
  }
}
