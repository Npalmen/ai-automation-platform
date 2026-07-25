# Post-2G roadmap audit

**Plan:** `docs/plans/post-2g-roadmap-audit.md` v1  
**Auditdatum:** 2026-07-25  
**Auditbaseline:** `origin/main @ 9c16f66f6cddcf5ea5fb8e1e26b4a312ea9d354a`  
**Förväntad baseline:** `632a15955c82b62a17b26f5b87d1c36b0d329ef4`  
**Baselineavvikelse:** 1 commit efter 2G-closure — begriplig, grön, roadmap-neutral (se § Verified baseline)  
**Metod:** Read-only — ingen kod-, dokumentations-, Git- eller extern ändring

---

## Executive decision

**Rekommenderat nästa huvudkapitel:** **Kapitel 13 — Fas 2 första kundpilot (go-live, morgoncockpit och godkännandeyta)**

**Kärnbeslut:** Efter stängt Kapitel 2G är den största luckan inte mer eval eller mer backend för Receptionisten — utan **produktifiering av Fas 1 mot första verkliga kundpilot**. Teknisk Fas 1 är bred och testad; kunden kan inte uppleva “arbetsdagen är förberedd”, godkänna åtgärder i primär yta, eller passera go/no-go. Master plan pekar uttryckligen på **Fas 2 — First Customer Productable Pilot** som aktuell fas (`docs/00-master-plan.md` §Fas 2).

**Nästa Cursor-plan ska skrivas för Kapitel 13.** Eval-arbete (2H) behövs inte före detta.

---

## Verified baseline

### Git

| Item | Värde |
|---|---|
| `origin/main` | `9c16f66f6cddcf5ea5fb8e1e26b4a312ea9d354a` |
| Senaste commit | `docs(2g): mark chapter 2G execution plan todos complete` |
| Commits efter förväntad 2G-baseline | 1 (`9c16f66` — endast `docs/plans/2g-execution-plan.md` todo-status) |
| Produkt-/eval-/driftpåverkan av avvikelse | **Ingen** — metadata-uppdatering endast |
| Lokal WIP | `?? storage/`, `?? docs/plans/post-2g-roadmap-audit.md` (auditartefakter) |

### Kapitel 2G closure (fortfarande sann)

| Kontroll | Status | Evidens |
|---|---|---|
| Closure marker i docs | ✅ | `docs/10g-generated-scenario-eval.md:40`, `docs/01-current-truth.md` rad ~1270 |
| Release Gate run | ✅ | `30170263775` — success (`gh run list --branch main`) |
| Artifact | ✅ | `2g-final-evidence-632a15955c82b62a17b26f5b87d1c36b0d329ef4` |
| `2g_final_report.json` | ✅ | `overall_status=passed`, `storage/status/2g-final-evidence-632a159/2g_final_report.json:110` |
| Todos A–E | ✅ | `docs/plans/2g-execution-plan.md` frontmatter — alla `completed` |
| 2G-kontrakt obrutna av `9c16f66` | ✅ | Ingen kod/workflow-ändring efter closure-SHA |

### CI / Release Gate (main)

| Run | SHA | Resultat |
|---|---|---|
| `30170515163` | `9c16f66` | **success** |
| `30170263775` | `632a159` | **success** — inkl. `eval-2g-main`, `final-2g-evidence` |
| `30169397598` | `ad34495` | failure — Docker Hub timeout (infra, ej 2G-logik) |

**Pytest inventory (lokal collect på `main`):** 4397 tests.

---

## Authoritative sources

| Dokument | Roll | Auditnotering |
|---|---|---|
| `docs/00-master-plan.md` | Högsta styrning | Fas 2 pilot = aktuell produktfas; kundportal React förbjuden (DEC-024 undantag endast operatör) |
| `docs/01-current-truth.md` | Verifierad sanning | 2G closure candidate; pilot `T_NIKLAS_DEMO_001` GO men soak ej körd; stale rader (Phase K, policy-gate) |
| `docs/02-first-customer-plan.md` | Första kund | 7-stegs liveflöde + 16 Phase L-gates + go/no-go — **alla soak-punkter ej klara** |
| `docs/06-backlog.md` | Backlog | “Next (Fas 2)” = 6 öppna pilotpunkter; 2G markerad complete |
| `docs/07-decisions.md` | Låsta beslut | DEC-015 (ingen kundportal), DEC-024 (operatörspanel), DEC-030 (pilot tenant) |
| `docs/08-runbook.md` | Drift | Deploy/backup-runbooks |
| `docs/09-testing-and-release.md` | CI closure | 2F/2G conditional closure modell |
| `docs/10f-live-eval-testbot.md` | Live eval | Authoritative Gmail `30050565974`, LLM `30131333378` |
| `docs/10g-generated-scenario-eval.md` | 2G | `2g-generator-v1`, `2g-mutation-v1`, PR 60 / main 160 |
| `docs/plans/2g-execution-plan.md` | Stängt kapitel | A–E completed |

**Saknad fil:** Ingen — alla listade källor finns.

---

## Current product truth

### Faskompetens (digital medarbetare)

| Fas / kompetens | Status | Evidens |
|---|---|---|
| Receptionisten — intake/klassificering | `verified_complete` | `app/workflows/orchestrator.py`, `classification_processor.py`; 74+30 receptionist-tester |
| Receptionisten — profiles/entities | `verified_complete` | `app/service_profiles/`, `entity_extraction_processor.py` |
| Receptionisten — lead/support/invoice | `verified_complete` | `lead_analyzer_processor.py`, `support_analyzer_processor.py`, `invoice_processor.py` |
| Receptionisten — policy/approval-first | `verified_complete` | `policy_processor.py`, `action_dispatch_processor.py`; `tests/test_email_approval.py` |
| Receptionisten — routing/handoff | `verified_complete` | `human_handoff_processor.py`, Monday adapter |
| Receptionisten — kundsvar (utkast) | `verified_complete` | Approval-gated; `tests/test_customer_reply_quality.py` |
| Receptionisten — notifieringar | `partial` | `app/admin/alerts/` — in-app ✅; e-post deferred (`OPERATOR_ALERT_RECIPIENT`) |
| Kontoret — Lead (Fas 2) | `partial` | Lead layer v2 + offer draft finns; ej separat produktkapitel |
| Kontoret — Support (Fas 2) | `partial` | Support analyzer v1; ej utökad produktresa |
| Kontoret — Ekonomi (Fas 2) | `partial` | Visma read/preview + approval export; ej autonom ekonomi |
| Kontoret — kundminne/regler | `planned_only` / `missing` | Inga dedikerade memory-moduler; tenant config only |
| Projektledaren | `planned_only` | Master plan Fas 5–6 |
| Företagschefen | `planned_only` | Master plan Fas 5–6 |

### Operatörsarbetsyta (`/ops`)

| Område | Status | Nyckelfiler |
|---|---|---|
| Overview | `verified_complete` | `frontend/src/features/overview/OverviewPage.tsx`, `app/admin/operations_overview.py` |
| Customers + onboarding wizard | `verified_complete` | `OnboardingWizardPage.tsx`, `app/admin/onboarding/routes.py` |
| Needs-help | `verified_complete` | `NeedsHelpQueuePage.tsx`, `operations_needs_help.py` |
| Incidents | `verified_complete` | `IncidentsPage.tsx`, `app/admin/incidents.py` |
| Alerts/digests | `verified_complete` | `AlertsPage.tsx`, `OperatorDigestsPage.tsx` |
| Usage | `verified_complete` | `UsagePage.tsx`, `app/admin/usage.py` |
| System status | `verified_complete` (read-only) | `SystemPage.tsx`, `app/admin/system_status.py` |
| Recovery actions UI | `missing` | API: `app/admin/recovery_actions.py`; ingen React-yta |
| Tenant morning cockpit i ops | `missing` | API finns (`/dashboard/cockpit`); React anropar ej |

### Kundarbetsyta

| Område | Status | Evidens |
|---|---|---|
| React kundportal | `missing` | `frontend/README.md`; DEC-015 + master plan förbud |
| Legacy kund-UI | `partial` | `app/ui/index.html` — kundläge finns |
| Legacy skrivrättigheter | `contradictory` | `LEGACY_UI_READ_ONLY = true` (`app/ui/index.html:2913`) blockerar POST inkl. approvals |
| Tenant APIs (results, activity, health) | `verified_complete` | `app/main.py` `/customer/*` |
| Dashboard/cockpit API | `verified_complete` | `app/main.py:2539` `dashboard_cockpit` |
| Kundgodkännanden i UI | `missing` | API `POST /approvals/{id}/approve` finns; ingen fungerande kundyta |

### Integrationer

| Integration | Status | Evidens |
|---|---|---|
| Gmail intake | `verified_complete` | `GoogleMailAdapter`, scheduler, dedup-tester |
| Gmail send (pilot) | `implemented_unverified` | Approval path finns; tenant OAuth send-gap i backlog |
| Monday | `verified_complete` | `MondayAdapter` — real write när konfigurerad |
| Google Sheets | `partial` | Manuell export only; `POST .../export-job` |
| Visma | `partial` | Approval-gated export; ej i default pipeline |
| Fortnox | `deferred_by_decision` | Read/preview/approval-gated per master plan |
| Internal stub | `verified_complete` | `InternalStubAdapter` när integration saknas |

### Eval och kvalitet (2E–2G)

| Komponent | Status | Evidens |
|---|---|---|
| Gold dataset k2e-v1 (20) | `verified_complete` | `docs/10e-gold-dataset-adversarial-coverage.md` |
| Live Gmail evidence | `verified_complete` | Run `30050565974` |
| Live LLM evidence | `verified_complete` | Run `30131333378` |
| 2F offline replay + final evidence | `implemented_unverified` | Job `final-2f-evidence`; ingen lokal `2f_final_report.json` |
| 2G generator + mutations | `verified_complete` | `2g-generator-v1`, `2g-mutation-v1` |
| PR/main batch + gates | `verified_complete` | `eval-2g-pr` (60), `eval-2g-main` (160), artifact passed |
| Failure corpus | `verified_complete` | `app/evaluation/batch/failures.py` |

**Största lucka efter 2G:** Produkt- och driftslucka (kundsynlighet, pilot go-live) >> testlucka.

### Autonomimodell i kod

Implementerad skala: `manual` → `approval_required` (`semi`) → `full_auto` (`auto`) — `app/workflows/tenant_automation.py`, `app/workflows/dispatchers/policy.py`.

Produktvisionens fyra nivåer (`informera`/`föreslå`/`efter godkännande`/`automatiskt`) är **inte** kodade som enum; presets i onboarding (`observe_only`, `prepare_only`, `approval_first`, `controlled_automation`) projicerar till `auto_actions` via `automation_projection.py`.

---

## First-customer journey

End-to-end-resa från avtal till daglig användning — faktisk status idag.

| # | Steg | Vem | UI/CLI | Manuellt? | Kundsynlighet | Operatörsynlighet | Status | Största friktion |
|---|---|---|---|---|---|---|---|---|
| 1 | Kund skapas | Operatör | `/ops/customers/new` → wizard | Delvis | Ingen | Full | `partial` | Kräver ops/admin; ingen self-serve |
| 2 | Integrationer ansluts | Operatör | Wizard `integrations` + `GmailIntegrationPanel` | Ja | Ingen | Full | `verified_complete` | OAuth-flöde fungerar; Gmail send ej verifierad live |
| 3 | Tjänster/regler konfigureras | Operatör | Wizard: modules, service_profile, automation, routing | Ja | Ingen | Full | `verified_complete` | Komplex wizard; kräver domänkunskap |
| 4 | Historik/profil etableras | Operatör | `data_start` step | Ja | Ingen | Full | `partial` | Begränsat kundminne; mest config |
| 5 | Första mejl tas emot | System | Scheduler / manuell scan | Auto vid scheduled | Indirekt | Full (jobs) | `implemented_unverified` | **Soak ej körd**; scheduler paused på pilot |
| 6 | Klassificering + förberedelse | System | Pipeline | Nej | Ingen direkt | Via customer detail | `verified_complete` | Kund ser inte “förberett arbete” |
| 7 | Kund/operatör granskar | Båda | Ops: needs-help; Kund: legacy (read-only) | Ja | **Saknas** | Delvis | `partial` | Kund kan ej godkänna i UI |
| 8 | Godkänd åtgärd utförs | System | `approval_dispatcher` | Nej | Resultat via API | Full | `implemented_unverified` | Live send ej verifierad |
| 9 | Resultat + uppföljning | Kund | `/customer/results`, legacy dash | Delvis | Delvis | Full | `partial` | Cockpit i legacy; read-only |
| 10 | Fel/osäkerhet | Operatör | needs-help, incidents, alerts | Ja | Minimal | Full | `verified_complete` | Recovery UI saknas i React |
| 11 | Användning/värde mäts | Kund/ops | `/ops/usage`, dashboard KPIs | Nej | API only | Full | `partial` | Wow/ROI ej i React kundyta |
| 12 | Ändra automationnivå | Operatör | `CustomerSettingsPage` automation | Ja | Ingen self-serve | Full | `partial` | Kund kan ej styra autonomi |
| 13 | Uppdatering/support | Operatör | Runbooks, deploy scripts | Ja | Ingen | Full | `partial` | Deploy ej från UI |

### Gap-karta (första kund)

```
Avtal ──► [✅ Ops onboarding wizard] ──► [⚠️ Gmail soak ej körd]
                                              │
                                              ▼
                                    [✅ Pipeline klassificerar]
                                              │
                         ┌────────────────────┴────────────────────┐
                         ▼                                         ▼
              [❌ Kund ser ej morgoncockpit]              [⚠️ Godkännande API only]
                         │                                         │
                         └────────────────► [❌ Go/no-go ej passerad]
```

---

## Morning experience gap

Produktprincip: *“När användaren öppnar produkten är arbetsdagen redan förberedd.”*

| Element | Klassificering | Evidens |
|---|---|---|
| Nytt sedan sist | Backend delvis; **saknas i primär yta** | `get_operational_insights` via cockpit API |
| Prioriterade leads | API ✅; React kund ❌; legacy dash ✅ | `dashboard_cockpit` buckets `actions_required`, `sla_risk` |
| Kundfrågor som behöver beslut | Ops needs-help ✅; kund ❌ | `NeedsHelpQueuePage` |
| Fakturor/ekonomiarbete | `underlag_ready` bucket i cockpit | `app/main.py:2550` |
| Utförda automatiska uppgifter | Dashboard activity API | `/customer/activity` |
| Väntande approvals | API + ops detail; **kund kan ej agera** | `LEGACY_UI_READ_ONLY` |
| Risker/avvikelser | Ops alerts/incidents ✅ | `/ops/alerts` |
| Rekommenderade nästa steg | Insights engine backend | Ej i React |
| Tydligt värde/sparad tid | ROI endpoints | Legacy/API; ej operatör-login-upplevelse |
| Operatör landar på “förberedd dag” | **Nej** — global overview | `OverviewPage` = plattform, ej tenant cockpit |
| Kund landar på “förberedd dag” | **Nej** — read-only legacy | `loadCockpit()` finns men writes blockerade |

**Slutsats:** Morgonupplevelsen är **implementerad i backend + legacy HTML** men **inte produktklar** i den yta kunden eller operatören primärt använder (`/ops`).

---

## Autonomy matrix

| Arbetsflöde | Informera | Föreslå | Efter godkännande | Automatiskt | Kundkonfigurerbart |
|---|---:|---:|---:|---:|---:|
| Lead intake | ✅ | ✅ | ✅ default | ⚠️ policy | ⚠️ ops only |
| Första kundsvar | ✅ | ✅ draft | ✅ default | ❌ default | ⚠️ ops only |
| Support routing | ✅ | ✅ | ✅ default | ⚠️ | ⚠️ |
| Invoice routing | ✅ | ✅ | ✅ handoff | ❌ | ⚠️ |
| Offertutkast | ✅ | ✅ | ✅ approval | ❌ | ❌ |
| Sheets-export | ✅ | ❌ | ✅ manuell trigger | ❌ | ❌ |
| Monday-export | ✅ | ⚠️ | ✅ | ⚠️ full_auto risk | ⚠️ |
| Visma-underlag | ✅ | ✅ preview | ✅ approval export | ❌ | ❌ |
| Påminnelser | ⚠️ SLA insights | ⚠️ | ❌ | ❌ | ❌ |
| Kalender/uppföljning | ❌ | ❌ | ❌ | ❌ | ❌ |
| Interna notifieringar | ✅ alerts | ✅ digests | N/A | N/A | ❌ |

**Förklaring:** ✅ = tekniskt implementerat och verifierat i test; ⚠️ = delvis / policy-beroende / ej UI-exponerat; ❌ = saknas eller ej tillåtet by default.

**Säkerhetsgap:** `full_auto` kan skriva till Monday utan per-action human gate när tenant policy tillåter — dokumenterat i `docs/01-current-truth.md` automation audit.

---

## Product and operations gaps

### Kundvärde
- Morgoncockpit och approvals ej tillgängliga i primär kundyta
- Ingen upplevd “digital medarbetare har redan arbetat”
- Wow/ROI finns i API men ej paketerat för demo

### Produktbarhet
- Onboarding kräver operatör genom hela wizard
- Kund kan inte själv godkänna eller justera automation
- Legacy UI read-only blockerar självbetjäning

### Driftbarhet
- Recovery actions saknar React-UI
- Soak Dag 1 väntar på operatörsåtgärd (testmejl)
- Scheduler paused — korrekt för pilot men ej “autonom drift”

### Säkerhet och kontroll
- Autonomy presets finns men kundsynlig kontroll saknas
- AI decisioning → policy seam: authorization läser ej AI `send_for_approval` direkt (`decision_contract.py`)
- Monday full_auto risk vid fel policy

### Onboarding
- Wizard komplett för ops (`OnboardingWizardPage`, 9 steg)
- Saknas: standardiserat “nästa kund”-paket, kund-OAuth via invitation delvis (`invitation_routes.py`)

### Synlighet och UX
- `/dashboard/cockpit` + `/reports/daily-summary` ej i React
- Operator overview ≠ tenant morning view

### Integrationer
- Gmail read: produktklar; send: overifierad live
- Sheets: manuell; Visma: approval-gated; Monday: produktklar med policy-risk

### Affär
- Pricing ej definierat (`docs/06-backlog.md` — not started)
- Demo kräver operatör medverkan
- Ingen mätbart kundvärde i kundlogin

---

## Roadmap contradictions

| Konflikt | Rekommendation |
|---|---|
| `01-current-truth` policy-gate “FAIL-OPEN” vs AUDIT-BUG-02 FIXED | Uppdatera stale rad vid nästa docs-pass (ej i denna audit) |
| Backlog Phase K BLOCKED vs senare PASS | Behåll PASS; arkivera BLOCKED-rader |
| Backlog Slice 2B `[ ]` vs current-truth PASS | Markera complete i docs |
| Master plan “no React” vs DEC-024 operatörspanel | Behåll — undantag är låst |
| `10f` “2G next” vs 2G closed | 2G closed vinner; uppdatera 10f vid docs-pass |
| Test counts 3265→3589→3814→4397 | Olika snapshots; ej en reconciled siffra |
| 2F closure artifact saknas lokalt | Verifiera på CI/main SHA; 2G artifact finns |
| Fasgränser Receptionist/Kontoret | **Fortfarande praktiska** — Fas 1 backend klar, Fas 2 produktifiering ej |

**Roadmap ska justeras i innehåll (nästa docs-uppdatering), inte i fasordning:** Efter 2G → **Fas 2 pilot**, inte ny eval-kapitel. Nästa kapitel är **produktifiering av Fas 1**, inte start av Kontoret Lead/Support/Ekonomi som separata produktkapitel.

---

## Prioritization matrix

Poängskala 1–5 per kriterium. Viktad total = Σ(poäng × vikt).

| Kandidat | Kundvärde 25% | Operatör 15% | Synlig backend 15% | Säkerhet 15% | Beroenden 10% | Låg risk 10% | Ombyggnad 5% | Demo 5% | **Viktad total** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Fas 2 pilot go-live + kundsynlig yta** | 5 | 4 | 4 | 5 | 4 | 3 | 5 | 5 | **4.40** |
| Kundens morgonöversikt (fristående) | 5 | 3 | 5 | 4 | 4 | 4 | 4 | 5 | 4.35 |
| Första-kund-onboarding paketering | 4 | 5 | 3 | 4 | 5 | 4 | 4 | 3 | 4.05 |
| Autonomikontroll per arbetsflöde | 4 | 3 | 4 | 5 | 4 | 3 | 4 | 4 | 3.95 |
| Kundportal React (approvals) | 5 | 3 | 5 | 5 | 2 | 2 | 5 | 5 | 3.95 |
| Operatörspanel driftåtgärder | 3 | 5 | 3 | 4 | 5 | 5 | 3 | 2 | 3.75 |
| Användning/värdemätning | 4 | 3 | 4 | 3 | 4 | 4 | 3 | 4 | 3.65 |
| Backup/restore/incident closure | 3 | 5 | 2 | 5 | 4 | 4 | 3 | 2 | 3.55 |
| Integration completion/polish | 3 | 4 | 3 | 4 | 4 | 4 | 3 | 3 | 3.45 |
| Fas 2 Lead (nytt kapitel) | 3 | 2 | 2 | 3 | 2 | 2 | 2 | 3 | 2.45 |
| Fas 2 Support | 3 | 2 | 2 | 3 | 2 | 2 | 2 | 3 | 2.45 |
| Fas 2 Ekonomi | 3 | 2 | 2 | 3 | 2 | 2 | 2 | 2 | 2.30 |
| Kundminne/regler | 3 | 2 | 1 | 2 | 2 | 2 | 2 | 3 | 2.25 |
| Mer eval (2H) | 2 | 2 | 1 | 3 | 5 | 5 | 3 | 2 | 2.55 |

---

## Recommended next chapter

### Kapitel 13 — Fas 2 första kundpilot (go-live, morgoncockpit och godkännandeyta)

**Problem som löses:** Fas 1 är tekniskt verifierad men **inte produktklar för första betalande kund**. Pilottenant finns (`T_NIKLAS_DEMO_001`, DEC-030) men soak/go-no-go är öppen; kunden ser inte förberedd arbetsdag; godkännanden går inte via primär yta.

**Varför före alternativen:**
- Master plan Fas 2 är explicit aktuell fas
- 2E–2G stängd — eval ger inte mer kundvärde nu
- Morgoncockpit-backend finns redan — låg risk att exponera
- Fas 2 Lead/Support/Ekonomi bygger på ej verifierad live-pilot
- Full React kundportal blockerad av DEC-015 utan nytt beslut

**Kundsynligt slutresultat:**
- Inloggad kund (legacy eller avgränsad yta) ser morgoncockpit: vad som hänt, vad som väntar, vad som behöver beslut
- Kund kan godkänna/avslå approval-gated åtgärder säkert
- Synligt sparat värde (status, aktivitet, enkel ROI-indikator)

**Operatörssynligt slutresultat:**
- Tenant-scoped “morgonvy” i `/ops` för pilotkund
- Automatiserad go/no-go-checklista med PASS/FAIL
- Dokumenterad soak Dag 1-runbook med scriptstöd
- Tydlig pilotstatus: redo / blockerad / live

**Beroenden (redan klara):**
- Pipeline, approvals API, cockpit API, onboarding wizard, ops panel, 2G quality gates

**Uttryckligen inte ingår:**
- Full React kundportal (kräver DEC-ändring)
- Fas 2 Kontoret (Lead/Support/Ekonomi som nya moduler)
- Kundminne / långtidsregler
- Nya integrationer (Outlook, m.fl.)
- Mer eval (2H)
- Gmail/LLM workflow_dispatch
- Pricing/paketering (kan paralelliseras men ej blockerande)

**Största risk:** Pilot soak kräver operatörsåtgärd (riktiga testmejl) — dev-kapitel kan inte slutföra utan operatör. **Mitigation:** tydliga stop-gates + operator-runbook; kod levererar verifierings- och UI-stöd.

**Förväntad storlek:** Medium–large (3–6 todos, 2–4 PRs)

**Definition of done:**
- Alla 6 backlog-punkter under “Next (Fas 2)” verifierade eller explicit blockerade med evidens
- Go/no-go checklist i `02-first-customer-plan.md` kan fyllas med CI/lokal evidens
- Kund kan se cockpit + hantera minst ett approval-flöde end-to-end (testmiljö)
- Operatör ser tenant cockpit i `/ops`
- Inga nya externa eval-körningar krävs
- Release Gate green på merge-SHA

---

## Second and third choices

### Andra plats: Kundens morgonöversikt / digital medarbetare (fristående UX-kapitel)
**Poäng:** 4.35. Stark produktvisionsmatch; cockpit-API finns. **Väntar** om den foldas in i Kapitel 13; annars separat om pilot-go-live prioriteras operativt först.

### Tredje plats: Första-kund-onboarding paketering
**Poäng:** 4.05. Wizard finns; gap är standardisering och “nästa kund utan utvecklare”. **Väntar** tills pilot bevisat att nuvarande wizard räcker eller identifierat specifika stegsgap.

**Varför inte kundportal React nu:** DEC-015 + master plan förbud; högt scope; kräver nytt beslut före implementation.

**Varför inte Fas 2 Lead/Support/Ekonomi:** Risk att bygga Kontoret innan Receptionisten är live-verifierad (`docs/plans/post-2g-roadmap-audit.md` §13).

---

## Proposed todo structure

Föreslagen uppdelning för nästa Cursor-plan (Kapitel 13):

| Todo | Innehåll |
|---|---|
| `13-a-pilot-readiness-audit` | Read-only gap mot go/no-go + Phase L; scripted checklist |
| `13-b-tenant-cockpit-ops` | Tenant-scoped morgonvy i `/ops` mot `/dashboard/cockpit` |
| `13-c-customer-approval-surface` | Kundgodkännande inom DEC-ram (legacy write-enable för approvals ELLER smal beslutad yta) |
| `13-d-soak-and-live-verification` | Soak scripts, first-scan automation, operator runbook, evidenslogg |
| `13-e-go-no-go-closure` | PASS/FAIL rapport, docs-uppdatering, pilot status DEC-030 |

**Branch/PR-struktur:**
- `feat/13a-pilot-readiness` → PR
- `feat/13b-tenant-cockpit` → PR (kan stacka på 13a)
- `feat/13c-customer-approvals` → PR
- `feat/13d-soak-verification` → PR (operator-dependent)
- `feat/13e-go-no-go` → PR + merge till main

**Stop-gates:**
- Stop om produktionskod måste ändras utanför scope (t.ex. ny integration)
- Stop om gold dataset eller eval-kontrakt kräver ändring
- Stop om pilot soak kräver Gmail send utan godkänd safety review
- Stop om DEC-015 måste ändras för scope — eskalera beslut först

---

## Dependencies and exclusions

| Beroende | Status |
|---|---|
| 2G closure | ✅ `632a159`, artifact passed |
| 2F live evidence | ✅ Gmail + LLM runs authoritative |
| Ops panel | ✅ `/ops` production-ready |
| Onboarding wizard | ✅ 9 steg |
| Cockpit API | ✅ `dashboard_cockpit` |
| Approvals API | ✅ approve/reject endpoints |
| Pilot tenant | ✅ `T_NIKLAS_DEMO_001` baseline GO |
| Operator test emails for soak | ❌ **Blocker** — mänsklig åtgärd |

---

## Risk register

| Risk | Sannolikhet | Konsekvens | Evidens | Mitigation | Stop-gate |
|---|---|---|---|---|---|
| Starta Fas 2 Kontoret före live pilot | Medel | Hög | Backlog “Later”; lead layer redan partial | Prioritera Kapitel 13 | GO/NO-GO: Fas 2 Lead = NO-GO |
| Mer backend utan kundsynlighet | Hög | Medel | Cockpit API utan React | Exponera befintlig API | Kräv UI/demo i DoD |
| Kundportal före onboarding/kontroll | Medel | Hög | DEC-015 | Smal approval-yta först | DEC-ändring krävs för full portal |
| Produktionssätta före operatörsdrift | Låg | Hög | K12 GO, soak ej körd | Soak + go/no-go | Extern pilot NO-GO tills checklist grön |
| Autonomy UI ≠ backend safety | Medel | Hög | `full_auto` Monday risk | Visa effektiv policy i UI | Blockera full_auto i pilot preset |
| Roadmap/docs divergens | Hög | Medel | Stale rader i 01/backlog | Docs-pass i 13-e | — |
| Soak blockerad på operatör | Hög | Medel | `02-first-customer-plan.md:267` | Runbook + tydlig handoff | Stop dev; operator report |
| Legacy UI read-only | Hög | Hög | `LEGACY_UI_READ_ONLY:2913` | Scoped write for approvals | — |

---

## GO/NO-GO decisions

| Beslut | Status | Motivering |
|---|---|---|
| Fas 1 är tekniskt verifierad | **GO** | 4397 tester; 2E–2G closure; receptionist suites |
| Fas 1 är produktklar för första betalande kund | **NO-GO** | Ingen fungerande kundapproval-UI; soak ej körd; morgoncockpit ej i primär yta |
| Första externa pilot kan startas nu | **NO-GO** | Go/no-go checklist öppen; soak Dag 1 ej körd |
| Kundportal bör vara nästa kapitel | **NO-GO** | DEC-015; smal yta räcker i Kapitel 13 |
| Onboarding bör vara nästa kapitel | **NO-GO** (ensamt) | Wizard finns; paketering är tredje prioritet |
| Autonomikontroll bör vara nästa kapitel | **NO-GO** (ensamt) | Ingår delvis i Kapitel 13 |
| Fas 2 Lead bör startas nu | **NO-GO** | Lead layer finns; live pilot först |
| Fas 2 Support bör startas nu | **NO-GO** | Samma |
| Fas 2 Ekonomi bör startas nu | **NO-GO** | Visma approval path finns; pilot först |
| Kundminne bör startas nu | **NO-GO** | För tidigt; ingen implementation |
| Mer evalarbete behövs före produktarbete | **NO-GO** | 2G stängd; produktlucka större |
| Nästa kompletta Cursor-plan kan skrivas | **GO** | Detta beslutsunderlag komplett |

---

## Evidence index

### Git & CI
- `origin/main` → `9c16f66f6cddcf5ea5fb8e1e26b4a312ea9d354a`
- Release Gate `30170263775`, `30170515163` — success
- `storage/status/2g-final-evidence-632a159/2g_final_report.json`

### Pipeline & policy
- `app/workflows/orchestrator.py` — `BASE_PIPELINE`
- `app/workflows/dispatchers/policy.py` — `resolve_policy_authorization`
- `app/workflows/tenant_automation.py` — `normalize_automation_mode`
- `app/workflows/processors/action_dispatch_processor.py` — `_email_needs_approval`

### APIs
- `app/main.py:2539` — `dashboard_cockpit`
- `app/main.py:1918` — `daily-summary`
- `app/main.py` — `/approvals/pending`, `/approvals/{id}/approve`

### Frontend
- `frontend/src/routes/router.tsx` — `/ops` routes
- `frontend/src/features/overview/OverviewPage.tsx`
- `frontend/src/features/onboarding/OnboardingWizardPage.tsx`
- `app/ui/index.html:2913` — `LEGACY_UI_READ_ONLY`

### Tests (urval)
- `tests/test_receptionist_quality_sprint2.py` (74)
- `tests/test_receptionist_quality_sprint2b.py` (30)
- `tests/test_email_approval.py`
- `tests/evaluation/test_2g_closure.py` (19)
- Total collect: 4397

### Dokument
- `docs/00-master-plan.md` §Fas 2
- `docs/02-first-customer-plan.md` §Go/no-go, §Pilot baseline
- `docs/06-backlog.md` §Next (Fas 2)
- `docs/07-decisions.md` DEC-015, DEC-024, DEC-030
- `docs/10g-generated-scenario-eval.md`

### Onboarding & lifecycle
- `app/admin/onboarding/routes.py`
- `app/admin/tenant_lifecycle/routes.py`
- `app/admin/tenant_lifecycle/invitation_routes.py`

---

*Audit complete. No repository changes made. Report: `storage/status/post-2g-roadmap-audit.md`.*
