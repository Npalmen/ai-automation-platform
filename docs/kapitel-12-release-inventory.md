# Kapitel 12 — Release inventory och plan (Fas 1)

> **Status:** Fas 1 godkänd; **Slice 1 = PARTIAL** (2026-07-18)  
> **Datum:** 2026-07-18  
> **Förutsättningar:** Kapitel 1–11 PASS (enligt `docs/01-current-truth.md`)

---

## Kapitelstatus (K1–K11)

| Kapitel | Scope | Status | Kvarvarande manuellt / gap |
|---------|-------|--------|----------------------------|
| **1** | Operations shell, auth, roles | **PASS** | — |
| **1C** | Session cookie, `/ops` login | **PASS** | — |
| **2** | Global översikt | **PASS** | Placeholder operational data i vissa metrics (dokumenterat) |
| **3** | Kundlista + detalj | **PASS** | Ingen separat jobs-lista i React |
| **4** | Needs-help | **PASS** | 8B responsive PASS (4 vyer) |
| **5** | Säkra operatörsåtgärder | **PASS** | Endast allowlistade actions; recovery ej i React UI |
| **6** | Incidents | **PASS** | Responsive ej full K12-matris |
| **7** | Usage/capacity | **PASS** | AI cost `unknown`; automation rate `not_measured` |
| **8** | System/backup/deploy status | **PASS** | Ingen deploy-knapp; metadata write failures osynliga i API |
| **8B** | Responsive + test reset | **PASS** | `seed-baseline` SKIP-rapportering (kosmetisk) |
| **9** | Onboarding wizard | **PASS** | Fortnox wizard deferred; offsite OAuth revoke deferred |
| **10** | Operator alerts + digests | **PASS** | Snooze/suppress UI saknas på alert detail (API only) |
| **11** | Security hardening | **PASS** | CSP ej satt; F06 missing Origin accepterad |

**Accepterade risker (DEC-028 m.fl.):** F05 plaintext OAuth, F06 Origin, F15 single operator, F16 in-memory rate limit, CSP low.

**Deploy/migrationsskuld:** SQL migrations `009`–`011` + runtime `schema_migrations`; ingen Alembic; prod Caddyfile ej hämtad i VCS; offsite backup **ej konfigurerad** (runbook blocker).

---

## Produktfunktioner — React `/ops` vs backend

| Funktion | Backend | React `/ops` | Legacy `/ui` | Releasekritisk? |
|----------|---------|--------------|--------------|-----------------|
| Overview | `/admin/operations/overview` | `/ops` | Admin dashboard | Ja |
| Customers list/detail | `/admin/tenants/*` | `/ops/customers` | Admin overview | Ja |
| Onboarding wizard | `/admin/onboarding/*` | `/ops/customers/new`, `…/onboarding` | Wizard flow | Ja |
| Needs-help | triage aggregation | `/ops/needs-help` | Admin needs-help | Ja |
| Incidents | `/admin/incidents/*` | `/ops/incidents` | — | Ja |
| Alerts | `/admin/alerts/*` | `/ops/alerts` | — | Ja |
| Digests | `/admin/operator-digests/*` | `/ops/digests` | — | Ja (ops+) |
| Usage | `/admin/usage/*` | `/ops/usage` | KPI views | Ja (read) |
| System status | `/admin/system/status` | `/ops/system` | Integration health | Ja |
| Safe operator actions | `/admin/tenants/{id}/actions/*` | Customer + needs-help detail | Support console actions | Ja |
| Approvals approve/reject | tenant-scoped routes | Approve + reject via operator actions | Approvals UI | **Ja** — RB-04 PASS i React (K12 Slice 1) |
| Jobs list/detail | `/jobs`, `/admin/recovery/*` | Metrics only on customer detail | Job views | **Gap** — recovery API only |
| Manual review queue | `/manual-review/jobs` | Count on overview/customer | — | **Gap** — ingen dedikerad React-vy |
| Recovery | `/admin/recovery/*` | **Saknas** | Recovery console | **Gap** — API/scripts/legacy |
| Audit browse (cross-tenant) | audit routes | Per-tenant på customer detail | Admin audit | Delvis |
| Backups/deploy actions | scripts + status JSON | Read-only cards på `/ops/system` | — | Read OK; write N/A |
| Auth/roles | session + API key | `/ops/login` | localStorage admin key | Ja |

---

## Driftkomponenter

| Komponent | Plats | Verifierad? | K12-anteckning |
|-----------|-------|-------------|----------------|
| FastAPI app | `app/main.py`, Docker | Delvis (prod Phase A–G historiskt) | Ren deploy från baseline krävs |
| PostgreSQL 15 | `docker-compose.prod.yml` | Ja | Restore till separat DB — övning krävs |
| Caddy | `infra/Caddyfile.example` (ej prod truth) | Delvis | Hämta/diff prod Caddyfile |
| Scheduler/cron | app scheduler + cron docs | Tester finns | Missad run-övning |
| Migrations | `migrations/009–011`, `schema_migrations` | Tester | Ordning i deployplan |
| Backup | `scripts/backup_postgres.sh` | Script + metadata tests | Freshness + offsite = blocker? |
| Restore rehearsal | `scripts/restore_postgres_rehearsal.sh` | Script tests | Full RTO/RPO-övning saknas i K12 |
| Monitoring | `scripts/check_backup_freshness.sh`, health | Delvis | Extern health alerting — runbook |
| Operator alerts | K10 engine | PASS | Evaluation isolation övning |
| Frontend build | `frontend/` → Vite dist | CI build | Same-origin `/ops` serving |
| Integration credentials | DB `oauth_credentials` | DEC-028 accepted | Revoked credential övning |

---

## Legacy

| Yta | Status K11 | K12-mål |
|-----|------------|---------|
| `app/ui/index.html` + `/ui` | Deprecation banner | 410/redirect eller arkiv efter paritet |
| localStorage `LS_ADMIN_KEY` | Fortfarande i legacy | Ta bort med legacy |
| Legacy Visma OAuth `state=tenant_id` | Blockerad | Verifiera redirect |
| `GET /admin/alerts/run-all` | Borttagen (POST) | Regression |
| `POST /admin/tenants` (create) | Script-only | Behåll för scripts |
| Tenant legacy email alerts (`app/alerts/engine.py`) | Separat från K10 | Dokumentera scope |
| Dormant `approval_routes.py` | Ej mounted | Regression test |

---

# Obligatorisk planrapport (sektion 1–8)

## 1. Release scope

### Ingår i pilotreleasen (operatörspanel + backend)

- Session-baserad operatörspanel på `/ops` med roller `read_only` | `operations` | `admin`
- Golden paths A, B (delvis), C–H via backend + befintliga React-vyer där de finns
- Kundonboarding (K9), incidents, alerts, digests, usage, systemstatus
- Säkra operatörsåtgärder (pause/resume/reject) från customer/needs-help
- Security gate K11 (236+ tester)
- Backup metadata + restore rehearsal script (read-only status i UI)
- Pilot tenant read-only/sandbox-verifiering (ej riktiga kundmutationer)

### Explicit deferred (ej K12-build)

- Kundportal / self-service
- SSO, per-user IAM, WAF, SIEM
- OAuth token encryption (DEC-028 post-pilot)
- Fortnox onboarding wizard
- AI cost instrumentation, automation rate metrics
- Alert snooze/suppress UI på detail page (API finns)
- Dedikerade React-vyer: jobs browser, manual review queue, recovery console, global audit browser
- Deploy/backup trigger-knappar i UI
- Offsite backup automation (om ej konfigurerad före pilot → CONDITIONAL)
- CSP (low — rekommenderas i Caddy, ej blocker)

### Pilotbegränsningar

- En global operator (`ADMIN_USERNAME` / `ADMIN_ROLE`)
- Manuell tenant setup via onboarding wizard (assisted pilot OK)
- Gmail/Monday/Visma enligt tenant sandbox/read-only policy
- In-memory rate limits (per process)

---

## 2. Releaseblockerare

| ID | Severity | Fynd | Evidens | Påverkan | Sannolikhet | Verifiering | Åtgärd |
|----|----------|------|---------|----------|-------------|-------------|--------|
| **RB-01** | **High** | Offsite backup ej konfigurerad | `docs/runbooks/backup-and-restore.md` | Dataförlust vid disk/serverhaveri | Medel | `OFFSITE_BACKUP_COMMAND` tom; freshness script | **Releaseblockerande** tills restore PASS (Slice 1 får starta) |
| **RB-02** | **High** | Legacy `/ui` + localStorage admin key | `app/ui/index.html` | Parallell operatörssanning | Medel | Slice 1 script + kod | **PARTIAL PASS** — read-only, purge, inga writes; full fysisk borttagning ej krävd före pilot |
| **RB-03** | **Medium** | Ingen React recovery UI | Router saknar recovery | Operatör måste använda API/legacy för path H | Hög under incident | Golden path H | API/script-verifiering räcker för CONDITIONAL; full retirement kräver React ELLER dokumenterad API-runbook |
| **RB-04** | **Medium** | Approval-first i React | Needs-help + customer detail | Operatör kan missa kö (path B) | Medel | Golden path B + slice script | **PASS** — approve/reject via `/ops` operator actions (K12 Slice 1) |
| **RB-05** | **Medium** | Prod Caddyfile ej i repo | `infra/Caddyfile.example` | Header/TLS drift | Låg | Diff mot prod | Hämta prod config till säker lagring; verifiera headers |
| **RB-06** | **Accepted** | F05 OAuth plaintext | DEC-028 | DB leak → tokens | Låg med kompensation | Secret scan | Post-pilot encryption |
| **RB-07** | **Accepted** | F06 missing Origin | DEC-028 | Script clients | Låg | K11 E2E | Dokumenterat |
| **RB-08** | **Accepted** | F16 in-memory rate limit | DEC-028 | Multi-instance bypass | Låg pilot | Unit test | Edge limit senare |
| **RB-09** | **Non-blocking** | CSP saknas | K11 report | XSS impact reduction | Låg | Header check | Caddy CSP i K12 slice 2 |
| **RB-10** | **Non-blocking** | Alert suppress UI | K10 docs | Admin måste använda API | Låg | API test | Deferred UI |

**Kritiska öppna:** Inga nya **critical** utan åtgärd identifierade i inventory. **High:** RB-01, RB-02 avgör GO vs CONDITIONAL GO.

---

## 3. Golden paths (verifieringsplan)

| Path | Primär yta | Metod | Artefakter |
|------|--------------|-------|------------|
| **A — Ny pilotkund** | `/ops/customers/new` → onboarding → activate | API E2E + browser | `T_K12_PILOT_*`, audit events, `plan_hash`, scheduler paused |
| **B — Gmail → operatör** | Pipeline + `/ops` overview/needs-help | Synthetic job + test mail (sandbox) | Job ID, approval state, audit, idempotency |
| **C — Lead** | Pipeline + customer detail | `test_local_golden_path.py` + optional live | Service profile, routing, Sheets/Monday mock |
| **D — Support** | Pipeline + needs-help | `test_core_intelligence_quality.py` + synthetic | Risk/handoff, approval policy |
| **E — Faktura** | Pipeline | `test_swedish_extraction_quality.py` + policy tests | manual_review for inkasso |
| **F — Alert** | `/ops/alerts` + API | `kapitel10_e2e_verify.py` + K11 | dedup, lifecycle, digest |
| **G — Incident** | `/ops/incidents` | `test_admin_incidents.py` + browser | timeline, owner, resolve |
| **H — Recovery** | API `/admin/recovery/*` | `test_recovery_actions.py` + role matrix | read_only 403, audit fail-closed |
| **I — Daglig start** | `/ops` overview + alerts + needs-help + system | Browser walkthrough | All widgets load; inga falska gröna |

**Testtenant:** `T_K12_RELEASE_VERIFY` (skapa via onboarding, ej prod-kunddata).

**Externa side effects:** Alla writes disabled eller sandbox; `auto_actions` false; `allowed_integrations` begränsad.

---

## 4. Incidentövningar

| Scenario | Detektion | Förväntad respons | Verifiering |
|----------|-----------|-------------------|-------------|
| DB otillgänglig | `/health`, extern check | 503; ingen falsk alert persist; runbook | Stoppa db container lokalt |
| App nere | Caddy/health | Extern alert; ej healthy | Stoppa app container |
| Scheduler missad | system status + alert evaluator | Stale heartbeat alert; paused tenant tyst | Mock last_run |
| Integration revoked | readiness/health + alert | Warning/error; reconnect runbook | Revoke test token |
| Backup stale/misslyckad | `check_backup_freshness.sh` + system status | Alert; operator action | Touch metadata / corrupt file |
| Restore | `restore_postgres_rehearsal.sh` | Separat DB; RPO/RTO dokumenteras | Full övning Slice 2 |
| Deployfel | health fail | Rollback image; migration compat | Tag N-1 start |
| OAuth callback fel | Visma onboarding | state replay block; safe error | K11 tests + manual |
| Evaluator fel | alert engine | Isolerat fel; andra evaluators OK | Inject failure test |

---

## 5. Prestandaplan

### Profiler

| Profil | Tenants | Volym | Syfte |
|--------|---------|-------|-------|
| A | 1 | 5–20 mail/dag | Minimipilot |
| B | 10 | 20–50 mail/tenant/dag | Tidig portfölj |
| C | 25–50 | Burst, begränsad concurrency | Säkerhetsmarginal |

### Mätning (befintligt Python, ingen ny load platform)

Nytt script: `scripts/kapitel12_perf_baseline.py` — wrappa `httpx`/`requests` timing mot kritiska endpoints med session/API key.

**Endpoints:** `/health`, `/admin/operations/overview`, `/admin/operations/needs-help`, `/admin/tenants`, `/admin/alerts`, `/admin/alerts/summary`, `POST /admin/alert-evaluations/run`, `/admin/operator-digests`, onboarding readiness, activation plan, jobs list.

### Föreslagna releasegränser (baseline efter mätning)

| Metric | Mål (förslag) |
|--------|----------------|
| Read p95 | < 500 ms |
| Overview/needs-help p95 | < 1,5 s |
| Critical write p95 | < 2 s (exkl. extern sandbox) |
| Error rate under test | 0 % på golden paths |
| Duplicate scheduler/eval runs | 0 |
| Connection leaks | 0 |

---

## 6. Deploy / rollback

### Pre-deploy checklist

- `git status` clean; commit SHA taggad
- `env` validation (`ENV=production`, keys, `DATABASE_URL`)
- Fresh backup + metadata
- Pending migrations inventerade (`009`, `010`, `011`)
- Disk/DB connectivity
- Scheduler paused; external writes sandbox
- Health baseline

### Deployordning

1. Backup (verifierad)
2. Build image + `frontend` dist (baked eller static mount — verifiera Dockerfile)
3. Additiva migrations (`schema_migrations` + SQL files)
4. Start app → `/health` 200
5. Schema version check
6. Operator login `/ops`
7. Smoke golden paths (A, F, I)
8. Alerts/system status
9. Enable scheduler kontrollerat
10. Observera 15–30 min
11. Dokumentera release i `docs/01-current-truth.md`

### Rollback

- Previous image tag documented
- Stop scheduler → rollback app → verify health
- Migrations måste vara bakåtkompatibla (additiva only)
- DB restore endast vid dataskada
- Verifiera ingen dataförlust på rollback smoke

---

## 7. Legacy parity

### Paritetsmatris (sammanfattning)

| Legacy funktion | React motsvarighet | Paritet | Blockerar avveckling? |
|-----------------|-------------------|---------|------------------------|
| Admin dashboard/KPI | `/ops` overview | **Ja** | Nej |
| Tenant list/provision | customers + onboarding | **Ja** | Nej |
| Needs-help | `/ops/needs-help` | **Ja** | Nej |
| Support console actions | operator actions | **Delvis** (allowlist) | Nej för pilot |
| Approvals UI | reject + approve via operator actions | **Ja** | Nej |
| Jobs/recovery console | API only | **Nej** | **Ja** för full legacy removal |
| Wizard (old) | K9 wizard | **Ja** | Nej |
| Fortnox tools | deferred | **Nej** | Nej (deferred) |
| Customer mode i legacy | Ej operatörspanel scope | N/A | Nej |

### Avvecklingsregel

Legacy får stängas när:

- Golden paths A, F, G, I fullt i `/ops`
- Paths B, H verifierade via API + runbook (CONDITIONAL) eller React
- Inga scripts kräver HTML-UI (API key scripts OK)
- `/ui` → 410 eller redirect till `/ops`
- localStorage admin key borttagen
- Tester förhindrar återintroduktion

**Om approve/recovery saknas i React:** rekommendera **CONDITIONAL GO** med legacy read-only + API-runbooks, eller minimal React/API bridge — **inte** ny feature scope utan releaseblockerare-beslut.

---

## 8. Releasebeslut — kriterier

### GO

- Alla blockerande golden paths PASS
- Inga critical/high öppna utan acceptance
- Backup + restore rehearsal PASS
- Rollback verifierad
- Security gate 236+ PASS
- Prestanda profil A (minst) inom gränser
- Browsermatris K12 PASS (alla `/ops`-vyer)
- Legacy avvecklad **eller** explicit icke-blockerande med dokumenterad workaround
- Offsite backup OK **eller** explicit accepted med ägare

### CONDITIONAL GO

- Inga critical
- High riskaccepterade (RB-01, RB-02) med ägare + deadline + begränsad pilot (1–2 tenants)
- Workaround: API/scripts för recovery/approve; legacy read-only banner

### NO-GO

- Tenant leak, auth bypass, backup/restore fail, rollback fail
- Central golden path fail utan workaround
- Okontrollerad migration risk
- Externa writes inte säkra

---

# Rekommenderad slice-uppdelning (K12)

| Slice | Innehåll | PASS när |
|-------|----------|----------|
| **Slice 1** | Golden paths A–I + roller/tenant + contracts + approval React + legacy matrix | **PASS** (2026-07-18) |
| **Slice 2** | Backup/offsite infra, incident drills (unit), perf A/B, deploy artifacts | **PARTIAL** — RB-01 BLOCKED until pilot-server backup+restore |
| **Slice 3** | Full browser/a11y-matris, GO/CONDITIONAL/NO-GO-beslut | Ej startad |

**Kapitel 12 = PARTIAL** tills alla tre slices PASS och RB-01 restore PASS.

---

# Nästa steg (efter godkännande)

1. Godkänn denna plan (ev. justera RB-01/RB-02 mot GO vs CONDITIONAL).
2. Skapa `scripts/kapitel12_golden_paths_verify.py` (read-only/sandbox).
3. Kör Slice 1 verifiering.
4. Uppdatera `docs/01-current-truth.md`, `docs/06-backlog.md`, `docs/07-decisions.md` (DEC-029 release decision).

**Ingen produktkod förrän plan godkänts.**
