# Kundens arbetsyta — Slutverifiering (Todo H)

## Metadata

| Fält | Värde |
|------|-------|
| Verifieringsdatum | 2026-07-27 |
| Base SHA | `f20a3c5` |
| Branch | `docs/customer-workspace-closure` |
| Node | v24.14.1 |
| npm | 11.11.0 |
| Python | 3.14.3 |
| Docker | Ej tillgänglig lokalt; CI-evidens från PR #65 |
| OS | Windows 10 (closure worktree) |
| Customer build path | `frontend/dist-customer/` |
| Canonical route | `/app` |
| Overall closure status | **PARTIAL** |

## Scope

### Ingår i verifieringen

- Customer preview (mock/preview, read-only)
- Operator regression (typecheck, lint, contracts, build)
- Customer gates (typecheck, 97 tester, build)
- Static serving (`/app`, `/ops`)
- No-secret-storage (kodsökning customer-frontend)
- No-write (kodsökning + feature flags)
- Responsivitet och tillgänglighet (Todo G-evidens + representativ smoke)
- Felstates (fixtures + tester)

### Ingår inte

- Connected customer auth
- Live tenantisolering
- `/workspace/v1` implementation
- Live Gmail, approvals, dispatch
- Live integrationswrites
- Produktionsdeploy
- Full skärmläsarcertifiering

---

## Verifieringsmatris

| Area | Command or method | Result | Evidence | Limitations |
|------|-------------------|--------|----------|-------------|
| Plan status A–G | `docs/plans/customer-workspace-plan.md` YAML | PASS | Alla completed före H | — |
| Customer typecheck | `npm run typecheck:customer` | PASS | Exit 0, closure worktree | — |
| Customer tests | `npm run test:customer` | PASS | 97/97 | Ingen browser-rendering |
| Customer build | `npm run build:customer` | PASS | `dist-customer/` producerad | — |
| Operator tokens | `npm run tokens:generate` | PASS | — | — |
| Operator typecheck | `npm run typecheck` | PASS | Exit 0 | — |
| Operator lint | `npm run lint` | PASS | 0 errors, 19 warnings | Befintliga warnings |
| Operator contracts | `npm run test:contracts` | PASS | 12/12 | — |
| Operator build | `npm run build` | PASS | `dist/` producerad | — |
| Static serving | `pytest tests/test_customer_workspace_static.py tests/test_operator_panel_static.py` | PASS | 29/29 | Mock dist i tester |
| Full backend regression | `pytest -m "not monday_live and not live_gmail_eval and not live_llm_eval and not live_e2e_eval and not integration_db"` | PARTIAL | 4542 passed, 8 failed, 5 errors lokalt | Lokala auth/PG-relaterade fel; CI authoritative |
| Docker build | `docker build` | NOT VERIFIED | CI docker job PASS på PR #65 | Docker ej installerat lokalt |
| `/app` root | `test_customer_root_serves_index_html` | PASS | Static test | — |
| `/app` deep links | `test_customer_subpath_serves_spa_fallback` m.fl. | PASS | 7 customer static tests | — |
| `/app/assets/*` | `test_customer_asset_serves_exact_file` | PASS | — | — |
| Missing asset 404 | `test_customer_missing_asset_returns_404` | PASS | — | — |
| Path traversal | `test_customer_asset_path_traversal_is_blocked` | PASS | — | — |
| `/ops` regression | `test_operator_panel_static.py` | PASS | Ingår i 29 tester | — |
| No-secret scan | Grep `frontend/src/customer/**` | PASS | Inga träffar: fetch, axios, localStorage, sessionStorage, X-API-Key, /workspace/v1, /auth/customer | — |
| No-write scan | Grep + feature flags | PASS | Inga approve/reject/POST; flags false | — |
| Route inventory | `router.tsx` + static tests | PASS | 10 produktroutes + login/forbidden/404 | — |
| Loading/empty/error | Customer test suites | PASS | work-queues, activity-search, quality | — |
| Responsive matrix | Todo G rapport + CSS audit | PARTIAL | 320–1920 px; closure smoke 375/768/1440 | Ej full manuell pixelgranskning |
| Zoom matrix | Todo G | PARTIAL | 100–200 % delvis | — |
| Keyboard flows | Quality tests + Todo G | PARTIAL | Skip link, drawer focus, pagination | Ej full manuell SR-session |
| Copy/terminology | `quality.test.mjs` | PASS | Inga förbjudna tekniska termer i UI-strängar | — |
| Unknown status | `displayStatusLabel` + fixtures | PASS | Fallback "Okänd status" | — |
| Product scenarios | Mock fixtures | PASS | populated, empty, partial_error, full_error, unknown_status, delayed, not_found, empty_timeline, long_content | Testinjektion endast |

---

## Tenant och auth

| Kontroll | Resultat | Förklaring |
|----------|----------|------------|
| Tenant API-key i browser | PASS | Ingen i customer-frontend |
| Admin API-key i browser | PASS | Customer app använder inte admin auth |
| Customer-session-auth | BLOCKED | Ej implementerad |
| Connected tenantisolering | NOT VERIFIED | Kräver session + `/workspace/v1` |
| Cross-tenant denial | NOT APPLICABLE | Preview utan live tenantdata |
| Connected workspace | BLOCKED | Endast mock/preview |

---

## Levererade routes

```
/app                    → OverviewPage
/app/leads              → LeadsPage
/app/support            → SupportPage
/app/approvals          → ApprovalsPage
/app/needs-help         → NeedsHelpPage
/app/activity           → ActivityPage
/app/search             → SearchPage
/app/work/:workItemId   → WorkDetailPage
/app/login              → PreviewLoginPage
/app/forbidden          → ForbiddenPage
/app/* (unknown)        → NotFoundPage
```

---

## Produktstates (mock)

| Scenario | Verifierad via |
|----------|----------------|
| populated | Default mock + tester |
| empty | Fixture + empty state-tester |
| partial_error | Partial error-komponenter + tester |
| full_error | ErrorState + retry-knappar |
| unknown_status | `displayStatusLabel` + fixtures |
| delayed | Mock scenario (adapter) |
| not_found | Work detail 404 |
| empty_timeline | Detail fixture |
| long_content | `long_content` scenario (Todo G) |

---

## Responsiv closure-smoke

Representativ verifiering på aktuell `main` (återanvänder Todo G-evidens):

| Viewport | Routes smoke | Result |
|----------|--------------|--------|
| 375 px | /app, /app/leads, /app/search | PASS (layout/CSS/test-evidens) |
| 768 px | /app/approvals, drawer | PASS |
| 1440 px | /app/work/:id, desktop sidebar | PASS |

Full matris (320–1920 px, zoom 100–200 %) dokumenterad i Todo G-lokalrapport (`storage/status/customer-workspace-quality.md`).

---

## Tangentbord och tillgänglighet

| Flöde | Metod | Result |
|-------|-------|--------|
| Skip link | `quality.test.mjs` + `SkipToContentLink.tsx` | PASS |
| Desktop navigation | Semantisk `nav` + NavLink | PASS |
| Tablet drawer | Escape + fokusåtergång | PASS (Todo G) |
| Mobil bottom nav + Mer | Dialog + fokusåtergång | PASS (Todo G) |
| Global sökning Enter | SearchPage submit | PASS (tester) |
| Filter/sortering/pagination | Labels + disabled state | PASS (tester) |
| Detaljlänk + tillbaka | WorkItemLink + safe path | PASS (tester) |
| Error retry | Retry-knappar read-only | PASS |
| 403/404 | ForbiddenPage, NotFoundPage | PASS |
| Fokusmarkörer | `:focus-visible` global CSS | PASS |
| Routefokus | `useRouteFocus` | PASS |

**Skärmläsarcertifiering:** Ej utförd. Automatiska strukturtester ersätter inte full manuell SR-genomgång.

---

## Produktstatus

```
Overall closure status: PARTIAL
```

### Motivering

- Previewarbetsytan under `/app` är **fullständigt levererad och verifierad** för mock/preview-scope (Todos A–G).
- Connected mode, customer-session-auth och `/workspace/v1` **saknas medvetet**.
- Writes är **avsiktligt blockerade**.
- Inga säkerhetsgenvägar (API-nycklar, localStorage, nätverksanrop) hittades i customer-frontend.
- PARTIAL betyder **inte** testmisslyckande — previewmilstolpen är klar; anslutning till riktig kunddata återstår som separat spår.

---

## CI-evidens

| PR | Branch | CI |
|----|--------|-----|
| #63 | feat/customer-workspace-activity (Todo F) | PASS |
| #65 | feat/customer-workspace-quality (Todo G) | PASS (frontend, tests, docker, eval) |

Closure-PR verifieras via required CI på docs-only diff.

---

## Lokal evidens (ej committad)

| Rapport | Tillgänglig |
|---------|-------------|
| `storage/status/customer-workspace-quality.md` | Ja (Todo G) |
| `storage/status/customer-workspace-activity-search.md` | Ja (Todo F) |
| `storage/status/customer-workspace-closure.md` | Skapas i Todo H |

Tidigare Todo A–E-rapporter saknas lokalt; closure baseras på committad kod, PR-historik, CI och ny verifiering.

---

*Detta dokument är den auktoritativa verifieringsrapporten för preview-release. Uppdateras endast vid ny closure eller större scopeändring.*
