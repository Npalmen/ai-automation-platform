/**
 * Presentation-only copy for operator actions.
 * Safety and availability always come from backend available_actions.
 */

type ActionPresentation = {
  consequence: string
  primaryLabel: string
}

const PRESENTATION: Record<string, ActionPresentation> = {
  "tenant.pause_automation": {
    consequence:
      "Pausar automatisk bearbetning för kunden. Befintliga jobb ändras inte och inga externa system anropas.",
    primaryLabel: "Pausa automation",
  },
  "tenant.resume_automation": {
    consequence:
      "Återupptar automatisk bearbetning för kunden. Inga externa system anropas direkt av denna åtgärd.",
    primaryLabel: "Återuppta automation",
  },
  "tenant.scheduler.pause": {
    consequence:
      "Stoppar schemalagd inkorgssynk för kunden. Befintliga jobb påverkas inte och inga externa anrop görs.",
    primaryLabel: "Pausa scheduler",
  },
  "tenant.scheduler.resume": {
    consequence:
      "Återaktiverar schemalagd inkorgssynk för kunden. Inga externa anrop görs direkt av denna åtgärd.",
    primaryLabel: "Återuppta scheduler",
  },
  "approval.reject": {
    consequence:
      "Markerar det väntande dispatch-godkännandet som avslaget. Ingen extern dispatch eller export utförs.",
    primaryLabel: "Avslå godkännande",
  },
  "approval.approve": {
    consequence:
      "Godkänner det väntande godkännandet och utför den konfigurerade åtgärden enligt policy.",
    primaryLabel: "Godkänn",
  },
}

export function getActionPresentation(actionId: string): ActionPresentation {
  return (
    PRESENTATION[actionId] ?? {
      consequence: "Bekräfta att du vill utföra åtgärden.",
      primaryLabel: "Utför åtgärd",
    }
  )
}
