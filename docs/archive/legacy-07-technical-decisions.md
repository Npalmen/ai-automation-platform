> Archived document. Historical reference only. Current governing source is docs/00-master-plan.md.

# Decisions Log

## DEC-001
**Title:** Multi-tenant via API key auth  
**Date:** 2026-04-07 (revised 2026-04-11)  
**Status:** Accepted (revised)

### Context
Plattformen behöver tenant-separation tidigt utan att först bygga full auth-plattform.

### Original decision (superseded)
Tenant identifierades via request header `X-Tenant-ID` — client-controlled, ingen validering.

### Revised decision (current)
Tenant identifieras via `X-API-Key`-header. Nyckeln mappas server-side till `tenant_id` via `TENANT_API_KEYS`-env-variabeln (JSON-mapping). `X-Tenant-ID`-headern ignoreras i autentiserat läge.

**Dev mode:** om `TENANT_API_KEYS` är tom faller systemet tillbaka på `X-Tenant-ID` med en varning — acceptabelt enbart lokalt.

### Consequences
- Tenant är inte längre client-controlled i produktion
- API-nycklar konfigureras via `.env`, inte i kod
- `X-Tenant-ID` kvar som dev-fallback utan breaking change
- Adminverktyg får använda giltig `X-Admin-API-Key` tillsammans med explicit `X-Tenant-ID` för tenant-scopade endpoints när en operatör arbetar med vald kund; vanlig kund-/tenantåtkomst använder fortsatt `X-API-Key`

---

## DEC-002
**Title:** Stateless processors, stateful jobs  
**Date:** 2026-04-07  
**Status:** Accepted

### Context
AI-delen ska inte styra systemflödet fritt.

### Decision
Processors hålls stateless, medan jobb bär historik och tillstånd genom pipeline och persistence.

### Consequences
- Mer deterministisk orchestration
- Bättre spårbarhet
- Lättare att pausa/resume via approval-flöde

---

## DEC-003
**Title:** Backend-first before broader UI expansion  
**Date:** 2026-04-07  
**Status:** Accepted

### Context
Backend-kärnan är redan långt fram och bär den verkliga produktlogiken.

### Decision
Fokus ligger först på att stabilisera officiellt MVP-flöde och dokumentation, därefter tunt operator/admin UI.

### Consequences
- Mindre risk att UI byggs ovanpå rörlig logik
- Snabbare väg till demonstrerbar teknisk MVP

---

## DEC-004
**Title:** Single-file operator UI, no frontend build toolchain  
**Date:** 2026-04-10  
**Status:** Accepted

### Context
Operatörs-UI behövdes för approval-flöde och jobbvisning utan att introducera separat frontend-projekt.

### Decision
UI levereras som en enda `app/ui/index.html` servad av FastAPI via `HTMLResponse`. Ingen React, Vite eller separat build-process.

### Consequences
- Inget frontend-beroende att underhålla
- UI fungerar ur lådan med `uvicorn`
- Skalbarhet begränsad — acceptabelt för MVP-operatörs-UI

---

## DEC-005
**Title:** Visual UI Refresh scoped to polish on existing CSS tokens and dark shell  
**Date:** 2026-05-07  
**Status:** Superseded by DEC-006

### Context
Sprint 5 (Visual UI Refresh) i den övergripande SaaS-planen beskriver en Apple/glassmorphism-inspirerad CSS-refresh. Samtidigt har den befintliga UI:n redan ett fullständigt dark premium SaaS-shell (Slice 22) med ett moget CSS custom property-designsystem: surface-hierarki (`--bg`/`--surface`/`--surface-2`/`--surface-3`), border-system (`--border`/`--border-med`/`--border-hi`), text-hierarki (`--text`/`--text-muted`/`--text-dim`), accent/glow-tokens (`--purple`/`--blue`/`--glow-*`), status-tokens (`--success`/`--warning`/`--danger` med `-bg`-varianter), form-tokens (`--radius`/`--radius-sm`/`--radius-lg`/`--shadow`/`--shadow-sm`) samt KPI-, card-, badge-, pill- och empty-state-klasser. Att bygga en ny designriktning från noll riskerar regressioner, scope creep och onödig omarbetning.

### Decision
Sprint 5 Visual UI Refresh begränsas till en **polish-pass ovanpå befintliga CSS tokens och det befintliga dark premium shell**. Följande regler gäller:

1. **Inga nya design tokens utöver befintliga** — nya tokens får bara läggas till om ett konkret gap identifieras och motiveras (t.ex. `--glass-bg` om frosted panels krävs för specifik vy). Befintliga tokens (surfaces, borders, text, accents, status, shape, shadows) ska återanvändas.
2. **Ingen ny designriktning från noll** — inget färgschema-byte, ingen ny typografisk hierarki, ingen ny layout-approach. Förbättringar bygger vidare på det som redan finns.
3. **Polishåtgärder som är tillåtna:**
   - Justera spacing, padding, margin för bättre luft och fokus
   - Förbättra hover/focus/active-states med befintliga tokens
   - Lägga till subtila transitions/animationer (max 200ms)
   - Förbättra kontrast och läsbarhet inom befintlig färgpalett
   - Polisha empty states, loading states och error states
   - Finslipa mobilvy med befintliga responsive-regler
   - Lägga till `backdrop-filter: blur()` sparsamt på modaler/overlays (undvik på scroll-tunga vyer)
4. **Alla befintliga ID:n och JS-selectors ska behållas** — inga breaking changes mot JavaScript-logiken.
5. **Frontend-stack-lås (DEC-004) gäller fortsatt** — vanilla single-file HTML/CSS/JS, ingen build-toolchain.

### Consequences
- Sprint 5 blir ett snabbare, tryggare polish-pass istället för en riskfylld visuell omgörning
- Befintliga CSS-klasser och tokens som redan används av alla vyer behålls stabila
- Agenter som arbetar med Sprint 5 vet exakt vilka ramar de har
- Mobilvy och tillgänglighetspass (UI-07, UI-08) ingår fortfarande men bygger på befintligt designsystem

---

## DEC-006
**Title:** Premium grayscale B2B SaaS design system replaces purple-heavy aesthetic  
**Date:** 2026-05-18  
**Status:** Accepted (supersedes DEC-005)

### Context
SaaS-produktifieringen (Slice 7) kräver en mer professionell och säljbar visuell identitet. Det befintliga UI:et har ett dominerande lila/purple-tema (--purple, --purple-light, --purple-glow) som upplevs som flashigt och icke-enterprise. En B2B-köpare förväntar sig ett återhållet, premium-utseende med konservativa färger och tydlig hierarki. Dessutom är det befintliga dark-only-UI ett hinder — enterprise-kunder förväntar sig alternativ.

### Decision
Ersätt den lila designriktningen med ett premium grayscale B2B SaaS-system:

1. **Nytt primär-accent**: byt `--purple` → `--accent` med ett neutral blågrått värde (#4F7FFF eller liknande), behåll varianter för hover/glow
2. **Grayscale-first surfaces**: behåll dark mode som default, lägg till light mode toggle via CSS-klass på `<html>`
3. **Design tokens bevaras** — alla befintliga token-namn (`--bg`, `--surface-*`, `--border-*`, `--text-*`, `--success`, `--warning`, `--danger`) behålls men uppdateras i värde
4. **Alla befintliga HTML-ID:n och JS-selectors bevaras** — ingen breaking change mot JS-logiken
5. **Inga externa beroenden** — vanilla CSS, inline i befintlig single-file HTML (DEC-004 gäller)
6. **Light mode**: vit/ljusgrå bakgrund, mörkgrå text, samma accentfärg, via `.light-mode` på `<html>`
7. **Typography**: byt till system-font stack (`-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`) för native premium-känsla

### Consequences
- Enterprise-kunder uppfattar produkten som professionell och mogen
- Light/dark toggle ger flexibilitet för olika arbetskontexter
- Alla befintliga komponenter och vyer fungerar oförändrat (token-baserade)
- DEC-005 polish-regler gäller fortfarande för spacing, transitions, och hover-states