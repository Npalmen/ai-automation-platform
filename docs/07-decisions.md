# Decisions Log

## DEC-001
**Title:** Multi-tenant via request header in MVP  
**Date:** 2026-04-07  
**Status:** Accepted

### Context
Plattformen behöver tenant-separation tidigt utan att först bygga full auth-plattform.

### Decision
Tenant identifieras i nuvarande MVP via request header `X-Tenant-ID`.

### Consequences
- Enkel lokal testning
- Bra för teknisk MVP
- Inte slutlig produktionssäker auth-modell

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