# Kundens arbetsyta — Preview release

## Status

| Egenskap | Värde |
|----------|-------|
| Release type | Mock/preview |
| Connected customer data | Nej |
| Customer writes | Nej |
| Closure status | PARTIAL |

## Sammanfattning

Den första versionen av kundens arbetsyta levererar en separat, responsiv och read-only preview under `/app`. Arbetsytan visar hur företagets digitala medarbetare kan presentera leads, kundfrågor, godkännanden, behov av hjälp, aktivitet och sökresultat — med tydlig status, historik och felhantering — utan att koppla till produktionsdata eller tillåta åtgärder.

Grundprincipen är oförändrad: **Systemet arbetar. Kunden leder.**

## Vad som levererats

### Applikationsskal och navigation

- Separat customer entry (`frontend/customer.html`) och build (`npm run build:customer`)
- Canonical route `/app` med desktop-sidebar, tablet-drawer och mobil bottom navigation
- Mer-meny, previewindikator, skip link, routefokus och error boundary
- Sidor för förhandsvisning (`/app/login`), åtkomst nekad (`/app/forbidden`) och 404

### Produktvyer

| Route | Funktion |
|-------|----------|
| `/app` | Daglig översikt med prioriterade arbetsobjekt och sammanfattning |
| `/app/leads` | Leadkö med filter, sortering och pagination |
| `/app/support` | Kundfrågekö |
| `/app/approvals` | Read-only godkännandevy |
| `/app/needs-help` | Ärenden som behöver mänsklig hjälp |
| `/app/activity` | Aktivitetshistorik med typfilter |
| `/app/search` | Global sökning med allowlistade filter |
| `/app/work/:workItemId` | Detaljvy med sammanfattning, nuvarande läge och tidslinje |

### UX och kvalitet

- URL-state för filter, sortering, pagination och sökning
- Säker tillbaka-navigation från detaljvy
- Loading-, empty-, partial error- och full error-states
- Neutral hantering av okänd status
- Responsiv layout (mobil, surfplatta, desktop)
- Tangentbordsnavigering, synliga fokusmarkörer och grundläggande tillgänglighet
- Svensk kundcopy utan tekniska internbegrepp

## Produktgräns

Previewarbetsytan använder **endast exempeldata** från en typad mock-adapter i frontend. Det innebär:

- Ingen koppling till kundens produktionsdata
- Inga approvals kan godkännas eller avslås
- Inga mejl kan skickas eller besvaras
- Inga actions, retries eller statusändringar kan utföras
- Inga inställningar eller automationer kan ändras

Previewindikatorn (`Förhandsvisning · ej ansluten`) ska alltid visas i skalet.

## Teknisk leverans

| Komponent | Detalj |
|-----------|--------|
| Frontend | `frontend/src/customer/**` — isolerat från operatörspanelen (`/ops`) |
| Build | `vite.customer.config.ts` → `frontend/dist-customer/` |
| Serving | FastAPI serverar `/app`, `/app/{path}` och `/app/assets/*` |
| Docker | `Dockerfile` kör `npm run build:customer` och kopierar `dist-customer` |
| Tester | 97 customer-tester + static serving-tester + CI-gates |
| Data | `WorkspaceDataSource` mock-adapter; inga nätverksanrop i preview |

## Nästa naturliga utvecklingsspår

Följande steg är **inte** en del av denna release och har inga leveransdatum:

1. Customer-session-auth (`/auth/customer/*`)
2. Read-only `/workspace/v1` backend
3. Serververifierad tenantisolering
4. Connected read-only-läge med riktig tenantdata
5. Separat produktbeslut om approval-actions och writes

---

*Verifierad på `origin/main` @ `f20a3c5` (2026-07-27). Se `docs/customer-workspace/verification.md` för evidens.*
