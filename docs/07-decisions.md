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