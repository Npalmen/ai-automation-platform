# Kapitel 2A — Core Intelligence Current Truth Audit

> **Audit scope:** Commit `ceb527ef9d6664b8f3174b76d2a0f682f0e2a0be` **plus** aktuella lokala ändringar i working tree.  
> **Audit date:** 2026-07-20  
> **Branch:** `feature/onboarding-2.0`  
> **Deliverable:** Denna fil endast. Ingen produktionskod, tester eller andra dokument ändrades.

---

## Verification context

| Field | Value |
|-------|-------|
| Branch | `feature/onboarding-2.0` |
| Commit (HEAD) | `ceb527ef9d6664b8f3174b76d2a0f682f0e2a0be` |
| Working tree | **Inte ren** — 159 ändrade/otrackerade filer totalt |
| Python | 3.14.3 |
| Node | v24.14.1 |

### Reproducerbarhetsbegränsning

Auditen läste **både** committed kod vid `ceb527ef` **och** filer som endast finns eller skiljer sig i working tree. Slutsatser är märkta:

- **`[COMMITTED]`** — fil finns i `ceb527ef` utan tracked diff mot HEAD.
- **`[WORKING TREE]`** — fil är otrackerad eller har unstaged/staged diff mot `ceb527ef`.
- **`[COMMITTED + WT]`** — committed bas med lokala tillägg som kan påverka runtime om de körs från denna katalog.

**Inget i working tree ändrades, stashades eller återställdes under auditen.**

### Working tree — relevanta intelligence/workflow/policy/testfiler

#### Core intelligence pipeline `[COMMITTED]`

Ingen tracked diff mot `ceb527ef` för:

- `app/workflows/orchestrator.py`
- `app/workflows/processors/*` (alla aktiva processorer)
- `app/workflows/intelligence_safety.py`
- `app/workflows/approval_service.py`, `approval_dispatcher.py`
- `app/workflows/action_executor.py`
- `app/workflows/dispatchers/*`
- `app/workflows/workflow_definitions.py`
- `app/ai/schemas.py`, `app/ai/prompts/registry.py`
- `app/service_profiles/*`
- `app/lead/*`, `app/invoice/routing.py`

**Pipeline-, policy-, decisioning- och dispatch-slutsatser i denna rapport gäller committed kod**, om inte annat anges.

#### Intake / Gmail entry `[WORKING TREE]`

| File | Status | Relevans |
|------|--------|----------|
| `app/workflows/intake_enforcement.py` | Otrackerad | Fail-closed intake gate (`evaluate_intake_gate`) före jobbskapande |
| `app/workflows/intake_alerts.py` | Otrackerad | Alert-hook för blockerad intake |
| `app/main.py` | Tracked diff | Gmail sync anropar `evaluate_intake_gate` före pipeline (tillägg i WT) |
| `tests/test_onboarding_2_0.py` | Otrackerad | Tester för intake gate |

**Påverkan:** Intake-gate i Gmail-synk är **inte verifierad i committed `ceb527ef`** utan endast i working tree. Övrig pipeline efter jobbskapande är `[COMMITTED]`.

#### Övriga WT-filer (låg direkt påverkan på kärnintelligens)

Tracked diff: onboarding, admin session, OAuth, tenant config, frontend — utanför scope för processor/policy-kedjan.

Otrackerade tester: `tests/test_onboarding_smoke_gates.py`, `tests/test_tenant_deletion_parity.py`, `tests/test_alert_status_parity.py` — inte inkluderade i kvalitetsinventering för kärnintelligens.

### Utförda kommandon (riktade tester)

| Kommando | Varför | Resultat | Bevisar / bevisar inte |
|----------|--------|----------|------------------------|
| `python -m pytest tests/test_email_approval.py::TestLeadActionsEmailGate::test_auto_false_wraps_email_actions_as_needs_approval tests/test_email_approval.py::TestEmailActionTypes::test_contains_send_internal_handoff -q --tb=short` | Återverifiera att `send_internal_handoff` ingår i email approval-gate | 2 passed | Bevisar att `_EMAIL_ACTION_TYPES` inkluderar internal handoff och att approval-wrap sker vid `auto_actions=False`. Bevisar **inte** live Gmail-send eller post-approval execution. |
| `python -m pytest tests/test_core_intelligence_quality.py::TestDoNotTouchPolicyQuality -q --tb=short` | Bekräfta att risk/complaint-path ger policy hold och handoff | 2 passed | Bevisar deterministisk do-not-touch-policy i processor-chain. Bevisar **inte** live AI decisioning eller extern execution. |
| `python -m pytest tests/test_local_golden_path.py -k "debt_collection or safety_risk" -q --tb=short` | Bekräfta debt/safety golden paths → manual review | 5 passed | Bevisar att debt collection och safety risk detekteras och routas till manual review i deterministiska golden cases. Bevisar **inte** full pipeline med live LLM. |

---

## 1. Executive summary

### Övergripande status

Krowolfs kärnintelligens är en **körbar, flerstegs workflow-pipeline** med tydlig separation mellan AI-rekommendation (processorer), deterministisk authorization (policy, `auto_actions`, approval) och execution (action dispatch, controlled dispatch). Systemet är **mogent för deterministisk receptionist-logik** (klassificering, profiler, risk-keywords, kundsvar) men har **kritiska seams** kring AI decisioning → policy och **begränsad beslutsspårbarhet** (ingen version pinning, muterbar historik).

### Största styrkor

1. **Verifierad runtime-pipeline** via `WorkflowOrchestrator` och `POST_CLASSIFICATION_PIPELINES`.
2. **Fail-closed kundmail** — `_email_needs_approval` kräver explicit `auto`/`full_auto` för att kringgå DB-backed approval.
3. **Keyword-baserad risk** — `assess_content_risk` override i policy är ovillkorlig.
4. **Rik deterministisk testbas** — 250+ kvalitetstester utan live-LLM för svenska installationsscenarier.
5. **Invoice-path utan ACTION_DISPATCH** — inga automatiska externa faktura-skrivningar i pipelinen.

### Största risker

1. **Decisioning schema mismatch** — AI emitterar `auto_route`/`hold`; policy läser `send_for_approval`/`auto_execute` → AI decisioning påverkar sällan authorization; default `auto_execute` för lead/inquiry.
2. **`create_monday_item` utan action-level approval** — körs när ACTION_DISPATCH tillåts och integration är allowlistad.
3. **Semantic risk** — keyword-only `assess_content_risk`; hög confidence kringgår inte keywords men missade keywords tillåter `auto_execute`.
4. **Observability** — inget DecisionRecord; `reclassify` wipe:ar historik; ingen modell/prompt/tenant-config-version på job.
5. **Working tree** — intake-gate i Gmail ej i committed baseline; reproducerbarhet mellan miljöer kan skilja sig.

### Redo för Fas 2-fundament?

| Område | Bedömning |
|--------|-----------|
| Icke-exekverande fundament (kontrakt, datamodeller, dry-run, evaluation-infra) | **CONDITIONAL GO** |
| Decisioning-beroende flöden | **NO-GO** tills schemafelet är löst och regressionsskyddat |
| Externa automatiska handlingar | **NO-GO** tills decisioning-seam och Monday-gating är adresserade |

---

## 2. Current-truth pipeline

### Entry points

| Entry | File | Notes |
|-------|------|-------|
| API `POST /jobs` | `app/main.py` | Skapar job, kör `run_pipeline` |
| Gmail inbox sync | `app/main.py` `_run_gmail_inbox_sync` | Pre-classify, tenant gate; **WT:** intake gate |
| Approval resume | `app/workflows/approval_service.py` → `WorkflowOrchestrator.resume_after_approval` | Kör endast `ACTION_DISPATCH` |
| Admin recovery | `app/admin/recovery_actions.py` | reclassify / re_extract / retry |
| Verification pipeline | `app/main.py` `_run_verification_pipeline` | Separat, ingen LLM |

### Runtime-auktoritet

**`[COMMITTED]`** [`app/workflows/orchestrator.py`](app/workflows/orchestrator.py) `POST_CLASSIFICATION_PIPELINES` är den **verifierade runtime-auktoriteten** — anropas från `WorkflowOrchestrator.run()` rad 83–91.

[`app/workflows/workflow_definitions.py`](app/workflows/workflow_definitions.py) är **icke-auktoritativ / potentiellt oanvänd**:

- Exporterar `DEFAULT_WORKFLOW`, `get_base_steps()`, `get_post_classification_steps()`.
- **Inga imports** i kodbasen (sökning på modulnamn, funktionsnamn och symboler — 0 träffar utanför filen).
- **Inga testreferenser**.
- Innehåller **förkortad** pipeline (saknar `LEAD_ANALYSIS`, `DECISIONING`, `ACTION_DISPATCH` jämfört med orchestrator).
- **Slutsats:** Dokumentation eller framtida refaktorering får inte utgå från denna fil; orchestrator gäller.

### Stegordning per job_type

```
intake → classification → [type-specific branch] → [policy] → [action_dispatch?] → human_handoff → finalize
```

#### LEAD `[COMMITTED]`

```
INTAKE → CLASSIFICATION → ENTITY_EXTRACTION → LEAD_ANALYSIS → LEAD (AI) → DECISIONING (AI) → POLICY → ACTION_DISPATCH → HUMAN_HANDOFF
```

#### CUSTOMER_INQUIRY `[COMMITTED]`

```
INTAKE → CLASSIFICATION → ENTITY_EXTRACTION → SUPPORT_ANALYSIS → CUSTOMER_INQUIRY (AI) → DECISIONING (AI) → POLICY → ACTION_DISPATCH → HUMAN_HANDOFF
```

#### INVOICE `[COMMITTED]`

```
INTAKE → CLASSIFICATION → ENTITY_EXTRACTION → INVOICE (AI) → POLICY → HUMAN_HANDOFF
```

(Ingen `ACTION_DISPATCH` i invoice-grenen.)

#### UNKNOWN / övriga klassificerade typer `[COMMITTED]`

```
INTAKE → CLASSIFICATION → POLICY → HUMAN_HANDOFF
```

### Post-completion `[COMMITTED]`

Efter `COMPLETED`:

1. `dispatch_approval_request` — om approval request finns
2. `manual_review_handoff` — Gmail UNREAD + label vid `manual_review`
3. `maybe_auto_dispatch_job` — lead → Monday vid `full_auto` dispatch policy (separat från pipeline `create_monday_item`)

### Statusövergångar `[COMMITTED]`

`JobStatus`: `PENDING` → `PROCESSING` → `COMPLETED` | `AWAITING_APPROVAL` | `MANUAL_REVIEW` | `FAILED`

| Transition | Trigger |
|------------|---------|
| `AWAITING_APPROVAL` | `has_pending_approval(job)` efter pipeline |
| `MANUAL_REVIEW` | `requires_human_review` i resultat |
| `FAILED` | Steg-exception eller `action_dispatch.failed_count > 0` |
| Resume approve | `resume_after_approval` → endast ACTION_DISPATCH |

`derive_job_status()` (`app/workflows/derived_status.py`) — read-only, lagras ej.

### Parallella analyslager (viktigt)

| Lager | Processorer | Policy läser? | Action dispatch läser? |
|-------|-------------|---------------|------------------------|
| Deterministisk domän | `lead_analyzer_processor`, `support_analyzer_processor` | Nej | Ja (drafts, profiler, frågor) |
| AI scoring/routing | `lead_processor`, `customer_inquiry_processor` | Ja (confidence, routing) | Delvis |
| AI decisioning | `decisioning_processor` | Ja (`decision` — **schema mismatch**) | Nej |

---

## 3. Komponentmatris

| Komponent | Ansvar | Huvudfiler | Inputs | Outputs | Det/AI | Fallback | Testtäckning | Risk | Mognad |
|-----------|--------|------------|--------|---------|--------|----------|--------------|------|--------|
| Intake | Normalisera origin/content | `intake_processor.py` | `job.input_data` | Normaliserat content, `recommended_next_step` | Det | — | Låg direkt | Dubbel intake (`processors/universal_intake.py` ej i registry) | 7 |
| Classification | job_type + confidence | `classification_processor.py` | input, metadata | `detected_job_type`, `confidence`, `reasons` | AI + det fallback | `classify_email_type`, `assess_content_risk` | `test_core_intelligence_quality`, receptionist suites | Trippelklassificering (Gmail + pipeline) | 8 |
| Entity extraction | Strukturerade entiteter | `entity_extraction_processor.py` | input, classification | `entities`, `validation` | AI + det | Identity från intake | `test_swedish_extraction_quality` | — | 8 |
| Lead analyzer | Kvalificering, profiler, frågor | `lead_analyzer_processor.py` | entities, input, tenant | `lead_analysis`, `service_profile_type`, `generated_question_message` | Det | — | `test_service_profile_pipeline`, golden path | Policy läser ej analyzer | 8 |
| Lead AI | Score, routing | `lead_processor.py` | history | `lead_score`, `routing`, `confidence` | AI + fallback | Low confidence flags | receptionist suites | Överlapp med analyzer | 7 |
| Support analyzer | Ticket type, urgency | `support_analyzer_processor.py` | entities, input | `support_analysis`, `support_next_action` | Det | `status: skipped` on error | `test_swedish_extraction_quality` | — | 8 |
| Inquiry AI | Inquiry type, priority | `customer_inquiry_processor.py` | history | `inquiry_type`, `routing` | AI + fallback | — | receptionist suites | — | 7 |
| Invoice | Extrahering + routing overlay | `invoice_processor.py`, `invoice/routing.py` | history | `invoice_data`, `invoice_routing` | AI + det routing | — | `test_sprint5_phase1_value`, golden path | Ingen auto-dispatch | 8 |
| Decisioning | Nästa steg rekommendation | `decisioning_processor.py` | classification, extraction, lead/inquiry | `decision`, `target_queue`, `action_flags` | AI + fallback `manual_review` | — | `test_mvp_flow` (mockade värden) | **Schema mismatch mot policy** | 4 |
| Policy | Authorization | `policy_processor.py`, `intelligence_safety.py` | Alla upstream payloads | `decision`, `approval_route`, `recommended_next_step` | Det | Risk override | `test_core_intelligence_quality`, golden path | Default auto_execute | 7 |
| Action dispatch | Bygga/köra actions | `action_dispatch_processor.py`, `action_executor.py` | policy, analyzers, tenant settings | `actions_executed`, `pending_approval` | Det | Skip sentinels | `test_email_approval`, `test_auto_reply_handoff` | Monday utan approval | 7 |
| Human handoff | Approval request / manual review flag | `human_handoff_processor.py` | policy | `handoff_type`, `approval_request` | Det | No-op | `test_core_intelligence_quality` | — | 8 |

**AI harness:** `ai_processor_utils.run_ai_step` — confidence &lt; 0.70 → `requires_human_review`; LLM-fel → fallback payload, `used_fallback: true`.

---

## 4. Decision boundary map

### Vad AI rekommenderar

| Processor | Fält | Påverkar execution direkt? |
|-----------|------|----------------------------|
| Classification | `detected_job_type`, `confidence` | Indirekt via pipeline routing |
| Lead / Inquiry AI | `routing`, `lead_score`, `priority` | Via policy confidence flags |
| Decisioning | `decision` (`auto_route`/`manual_review`/`hold`) | **Avsedd** via policy — **bruten seam** |
| Invoice AI | `approval_route`, `invoice_routing` | Informativt; invoice har ingen dispatch |

### Vad deterministiska regler avgör

| Regel | Plats | Effekt |
|-------|-------|--------|
| `assess_content_risk()` | `intelligence_safety.py` | Policy → alltid `hold_for_review` vid träff |
| Policy per job_type | `policy_processor.py` | Invoice → approval/hold; unknown → hold |
| Low confidence | policy + `ai_processor_utils` | `hold_for_review` |
| `_email_needs_approval` | `action_dispatch_processor.py` | Fail-closed för email-typer |
| `resolve_dispatch_policy` | `dispatchers/policy.py` | CRM dispatch mode |
| `is_integration_enabled_for_tenant` | `integrations/policies.py` | Skip disallowed integrations |
| Orchestrator `_should_skip_step` | `orchestrator.py` | Skip hela ACTION_DISPATCH vid hold/approval |

### Vad tenant-konfiguration tillåter

| Setting | Effekt |
|---------|--------|
| `auto_actions[job_type]` | Email bypass (`True`/`auto`/`full_auto` only) |
| `allowed_integrations` | Blockar execution i `execute_action` |
| `automation.followups_enabled` | Skippar `send_customer_auto_reply` |
| `branding.internal_notification_email` | Mottagare för `send_internal_handoff`; saknas → `_skip` |
| `memory.routing_hints` / `external_routing_targets` | Controlled dispatch readiness |
| `force_approval_test` (job input) | Policy test hook → `send_for_approval` |

### Vad approval kräver

**Pipeline-level** (`[COMMITTED]`):

- Policy `send_for_approval` → `human_handoff_processor` skapar `build_approval_request`; orchestrator skippar ACTION_DISPATCH.
- Policy `hold_for_review` → skip ACTION_DISPATCH; job → `MANUAL_REVIEW`.

**Action-level** (`[COMMITTED]` — återverifierad):

| Action | I `_EMAIL_ACTION_TYPES`? | Approval-villkor | Övriga villkor |
|--------|--------------------------|------------------|----------------|
| `send_customer_auto_reply` | Ja | `_needs_approval` om `risk_detected` ELLER `_email_needs_approval(job_type, settings)` | `_skip` om `followups_enabled=false` eller saknad kund-email; risk → `_build_sensitive_customer_ack` har inbyggd `_needs_approval` |
| `send_internal_handoff` | **Ja** | **Samma gate som kundmail** — rad 493–498 (lead) / 728–733 (inquiry) wrappar alla `_EMAIL_ACTION_TYPES` | `_skip` om `internal_notification_email` saknas |
| `create_monday_item` | Nej | **Ingen** action-level approval | Körs om ACTION_DISPATCH körs; blockeras av `integration_not_allowed` eller stub om ej konfigurerad |
| `send_email` | Ja | Samma email-gate | Generisk email-action |

**DB-backed approval:** `_create_email_approval_record` → `ApprovalRequestRepository`; `next_on_approve: email_send`; resume via `resolve_approval` / `email_approval_resolution.py`.

**Korrigering mot tidigare audit-hypotes:** `send_internal_handoff` **har** action-level approval-gate (delad med kundmail). Det som **saknar** action-level approval är `create_monday_item` (och post-completion `maybe_auto_dispatch_job` under separat policy).

### Vad dispatch faktiskt utför

| Action | Integration | Beteende |
|--------|-------------|----------|
| Email-typer | `GOOGLE_MAIL` | Riktig adapter om konfigurerad; annars `InternalStubAdapter` |
| `create_monday_item` | `MONDAY` | Riktig adapter om konfigurerad; annars stub |
| Controlled dispatch | `ControlledDispatchEngine` | Operator eller `full_auto` post-completion; `approval_required` blockerar live write |

---

## 5. Kod–test–dokumentationsavvikelser

| ID | Dokumentation / test | Faktisk kod | Konsekvens | Resolution |
|----|---------------------|-------------|------------|------------|
| **S1** 🔴 | Decisioning styr policy (`docs/ai-receptionist-mvp-gate-results.md`; `test_mvp_flow` injicerar `send_for_approval`/`auto_execute`) | AI schema: `auto_route`/`hold` (`schemas.py:110`); policy läser `send_for_approval`/`auto_execute` (`policy_processor.py:177-235`); else → `auto_execute` | AI decisioning påverkar inte authorization i produktion | Mappa schema i policy eller ändra AI schema; regressionstest med live AI-värden |
| **S2** 🔴 | `create_monday_item` alltid säkert p.g.a. approval-first | Monday körs utan `_needs_approval` när policy tillåter ACTION_DISPATCH (`test_email_approval.py::test_auto_false_monday_not_wrapped`) | Extern CRM-write utan mänsklig gate vid `auto_execute` + allowlist | Action-level approval eller policy-hold för Monday |
| S3 | `workflow_definitions.py` beskriver pipeline | Inga runtime-imports; orchestrator skiljer sig | Felaktig läsning av pipeline | Markera icke-auktoritativ; uppdatera referenser vid behov |
| S4 | Full decision trace | `reclassify` nollställer `processor_history` (`recovery_actions.py:257`) | Förklarbarhet försämras vid recovery | Append-only supersede (DecisionRecord) |
| S5 | Risk policy täcker semantisk risk | `assess_content_risk` är keyword-only | Semantic high-risk kan nå `auto_execute` | Utvärdera harness + kompletterande detektor (ej i detta kapitel) |
| S6 | `test_email_approval.py` modul-doc: "auto_actions missing → emails execute immediately" | `_email_needs_approval` returnerar `True` vid saknad key; tester rad 142–147 bekräftar approval-wrap | Förvirrande docstring | Rätta docstring i framtida PR (ej detta kapitel) |
| S7 | Intake gate i drift | `intake_enforcement.py` + `main.py` wiring endast i WT | Committed baseline saknar Gmail intake gate | Verifiera vid merge; dokumentera i 01-current-truth efter merge |

🔴 = säkerhetskritisk

---

## 6. Evaluation inventory

### Test- och scenariokällor

| Källa | Antal tester (ca.) | Typ | Vad den verifierar |
|-------|-------------------|-----|-------------------|
| `test_core_intelligence_quality.py` | 11 | Det processor-chain | Klassificering, kvalificering, risk, policy hold, kundsvar |
| `test_swedish_extraction_quality.py` | 61 | Det | Adress, orgnr, OCR, invoice risk, support urgency |
| `test_receptionist_quality_sprint2.py` | 74 | Det pipeline | 12 scenarier, routing, approval hints |
| `test_receptionist_quality_sprint2b.py` | 30 | Det | Utökade scenarier, `_email_needs_approval` |
| `test_customer_reply_quality.py` | 50 | Det | Reply tone, approval, inga bindande löften |
| `test_service_profile_pipeline.py` | 34 | Det | Profiler, missing info, pipeline payload |
| `test_local_golden_path.py` | 20 | Det golden | EV, solar, debt, safety, tenant hints |
| `test_email_approval.py` | 40+ | Det + mock DB | Email approval gate, Monday ej wrapped |
| `test_auto_reply_handoff.py` | 25+ | Det | Auto-reply, internal handoff, skip-villkor |
| `test_mvp_flow.py` | få | Det mock decisioning | Policy/approval med **fabricerade** decisioning-värden |
| `docs/ai-receptionist-test-mail-scenarios.md` | 8 manuella | Gmail E2E (ej CI) | End-to-end mot riktig inkorg |
| `scripts/run_release_gate_r1` | regression + E2E | Blandat | Release gate, inte kvalitetsgolden |

### Kategoritäckning (12 kategorier)

| Kategori | Täckt? | Källa | Lucka |
|----------|--------|-------|-------|
| lead | Ja | receptionist, golden path, core intelligence | — |
| support | Ja | receptionist, swedish extraction | — |
| customer inquiry | Ja | receptionist, core intelligence | — |
| invoice | Ja | sprint5, golden path, invoice tests | — |
| spam | Delvis | classification fallback | Få dedikerade scenarier |
| unknown | Delvis | classification tests | — |
| juridisk risk | Ja | `assess_content_risk`, core intelligence | Keyword-only |
| säkerhetsrisk | Ja | electrical fault, emergency keywords | — |
| reklamation | Ja | complaint path i inquiry actions | — |
| dataskydd | Delvis | `data_deletion` i core intelligence | Ingen bred GDPR-harness |
| prompt injection | **Nej** | — | **Inga tester** |
| externa actions | Delvis | `test_action_executor_monday`, integration gating | Live LLM + live extern write ej i CI |

### Mäter testerna verklig kvalitet?

- **Ja (deterministisk domän):** svenska keywords, profiler, risk, reply-innehåll.
- **Nej (modellkvalitet):** AI-steg mockas eller körs med fallback; ingen systematisk LLM-eval i CI.
- **Teknisk funktion vs kvalitet:** majoriteten verifierar att rätt processor körs och payload shape — inte att LLM klassificerar korrekt i produktion.

### Föreslaget minimalt scenarioformat (för 2C harness)

```yaml
scenario_id: lead_ev_charger_001
category: lead
source: committed  # eller working_tree
input:
  subject: "Offert laddbox hemma"
  message_text: "..."
  sender: {name: "Erik", email: "erik@example.com"}
tenant:
  auto_actions: {lead: false}
  internal_notification_email: "sales@example.com"
assertions:
  classification: {job_type: lead}
  policy: {decision_in: [hold_for_review, send_for_approval, auto_execute]}
  risk: {detected: false}
  actions:
    send_customer_auto_reply: {needs_approval: true}
    send_internal_handoff: {needs_approval: true}
    create_monday_item: {present: true, needs_approval: false}
  reply:
    not_contains: ["Hej Niklas"]
```

### Återanvändbara fixtures

- `_make_job`, `_settings` från `test_auto_reply_handoff.py`
- `_lead_job` / receptionist helpers från `test_receptionist_quality_sprint2.py`
- 8 scenarier från `docs/ai-receptionist-test-mail-scenarios.md`
- Golden cases från `test_local_golden_path.py`

### Första scenariofamiljer (2D)

1. Low-risk lead med approval-gated email  
2. High-risk / safety (hold, sensitive ack)  
3. Debt collection invoice  
4. Complaint inquiry  
5. Data deletion request  
6. Prompt injection (ny)  
7. `auto_actions: full_auto` med Monday execution  
8. Unknown / spam  

---

## 7. Observability gap analysis

### Vad systemet sparar idag `[COMMITTED]`

| Data | Lagring |
|------|---------|
| Processorresultat | `jobs.processor_history[]`, `jobs.result` |
| Beslut/orsaker/confidence | Processor payloads; policy aggregerar |
| Audit events | `audit_events` (steg start/slut, approval, recovery) |
| Approvals | `approval_requests` + `decision_context` snapshot |
| Externa actions | `action_executions`, `integration_events` |
| Tenant config version | `tenant_configs.config_version` — **ej kopierad till job** |
| Operatör | `audit_events` category `operator_action` |

### Kan systemet svara på…?

| Fråga | Idag | Gap |
|-------|------|-----|
| Vad visste systemet? | Delvis via processor_history | Ingen sammanhållen DecisionRecord |
| Vilken kod/regel/prompt/config-version? | `prompt_name` ibland | Ingen modellversion, prompt-hash, policy-version, config_version på job |
| Vad rekommenderades? | Ja, per processor | Decisioning rekommendation ej kopplad till policy outcome |
| Vad tillät policyn? | Ja, policy payload | — |
| Vad utfördes? | action_executions | Stub vs live ej alltid tydligt i UI |
| Vad ändrade operatören? | Approval resolve, manual review resolve | Ingen strukturerad correction record; reclassify wipe |
| Faktiskt utfall? | Job status + executions | Svårt att reproducera exakt |

### Operatörskorrigeringar idag

| Mekanism | Historik bevarad? |
|----------|-------------------|
| Approve/reject approval | Ja |
| Resolve manual review | Ja (audit) |
| reclassify | **Nej** — history wipe |
| re_extract | Delvis — strip ett steg |
| Lead status override i input_data | Ad hoc fält |

---

## 8. Föreslaget DecisionRecord-kontrakt (minimalt, logiskt)

**Ansvar:** En append-only, terminal förklaringspost per jobbförsök som binder ihop rekommendation, policy, approval och execution med versionerade referenser.

**Ej i scope:** migration, API, UI.

```yaml
DecisionRecord:
  decision_id: uuid
  tenant_id: string
  job_id: string
  source_message_id: string | null
  created_at: datetime

  decision_type: policy | approval | operator_override | recovery_rerun
  outcome: auto_execute | send_for_approval | hold_for_review | approved | rejected | manual_review_resolved
  reasons: string[]
  confidence: float | null

  input_fingerprint: string
  processor_chain:
    - processor_name: string
      prompt_ref: {name, content_hash} | null
      model_ref: {provider, model} | null
      output_summary: object
      used_fallback: bool

  context_versions:
    tenant_config_version: int
    service_profile_ref: {type, hash}
    policy_rule_set_version: string
    pipeline_version: string

  approval_id: uuid | null
  operator_action:
    actor_id: string
    action: string
    reason: string | null
    supersedes_decision_id: uuid | null

  actions_executed: [{execution_id, action_type, status, external_id}]
  audit_event_ids: string[]
```

**Regler:**

1. Append-only — korrigering skapar ny post med `supersedes_decision_id`.  
2. Pin `tenant_config_version` vid intake.  
3. Recovery får inte radera `processor_history` utan supersede-länk.  
4. Terminal post = förklaringsankare för operatör och eval harness.

---

## 9. Rekommenderade kvalitetsgrindar

### Absoluta säkerhetskrav (måste PASS)

- Risk keyword → policy `hold_for_review` (befintligt beteende).
- Kundmail fail-closed utan explicit `auto`/`full_auto`.
- Invoice-path utan ACTION_DISPATCH / inga automatiska ekonomi-skrivningar.
- Tenant isolation på job/approval/audit.
- Inga bindande juridiska/ekonomiska löften i auto-reply utan approval (sensitive ack).
- **Efter fix:** decisioning-värden ska mappas deterministiskt till policy (`auto_route` → ej blind `auto_execute`).

### Kvalitetsmål (bör PASS på golden set)

- ≥95% korrekt `job_type` på golden dataset (deterministisk + LLM-offline replay).
- 8 receptionist-doc-scenarier PASS i harness.
- Safety/debt/complaint → aldrig `auto_execute` utan hold.
- Internal handoff + customer reply approval-symmetri vid fail-closed config.

### Framtida optimeringsmål

- LLM confidence calibration.
- Semantic risk utöver keywords.
- Svarskvalitet (ton, personalisering) — human rubric.

---

## 10. Kapitelplan 2B–2E

### 2B — DecisionRecord & version pinning

| | |
|--|--|
| **Mål** | Minimalt kontrakt, append-only persistence, pin `tenant_config_version` + prompt/model refs på job |
| **Avgränsning** | Ingen full operatör-UI; inga nya produktfeatures |
| **Beroenden** | 2A (denna audit) |
| **Filägarskap** | Ny `app/workflows/decision_record.py`, migration, hooks i `orchestrator.py` / `policy_processor.py` |
| **Parallellt** | Schema-agent + orchestrator-hook-agent |
| **Integration** | `audit_events`, `approval_requests`, `action_executions` |
| **Avslut** | Terminal decision queryable; reclassify appendar supersede |
| **Tester** | Fokuserade unit + ett integrationstest för pin fields |

### 2C — Lokal evaluation harness

| | |
|--|--|
| **Mål** | YAML-driven runner, deterministisk default, återanvänder receptionist-fixtures |
| **Avgränsning** | Ingen live LLM i CI default |
| **Beroenden** | 2A scenarioformat; gärna 2B för version fields i assertions |
| **Filägarskap** | `tests/eval/`, `scripts/run_eval_harness.py` |
| **Parallellt** | Fixture-migrering + runner |
| **Avslut** | 20+ scenarier PASS lokalt |
| **Tester** | Harness self-test + golden smoke |

### 2D — Golden dataset

| | |
|--|--|
| **Mål** | Kuraterad dataset, baseline scores, täck alla 12 kategorier inkl. prompt injection |
| **Beroenden** | 2C harness |
| **Filägarskap** | `tests/eval/golden/*.yaml` |
| **Avslut** | Documented baseline; gap report per kategori |
| **Tester** | Harness körs mot golden i CI (deterministisk del) |

### 2E — Gmail testbot

| | |
|--|--|
| **Mål** | Automatisera 8 doc-scenarier mot test-tenant inbox |
| **Beroenden** | 2C assertions; test-tenant credentials |
| **Filägarskap** | `scripts/gmail_testbot.py` |
| **Avgränsning** | Read-only mot prod; egen test-tenant |
| **Avslut** | 8/8 scenarier körbara manuellt eller i scheduled job |
| **Tester** | Dry-run mode unit tests |

**Integrationsordning:** 2B ∥ 2C (delvis) → 2D → 2E.

---

## 11. Slutbedömning

### Ändrade filer i detta kapitel

- `docs/10a-core-intelligence-audit.md` (skapad)

### GO / NO-GO

| Beslut | Status | Motivering |
|--------|--------|------------|
| **DecisionRecord** | **GO** | Tydligt gap; minimalt kontrakt definierat; append-only löser reclassify-problem |
| **Lokal evaluation harness** | **GO** | Stark återanvändning av befintliga tester; scenarioformat klart |
| **Golden dataset** | **GO** | Efter harness; explicit lucka prompt injection |
| **Gmail-testbot** | **CONDITIONAL GO** | Kräver test-tenant + harness; inte före 2C |
| **Fas 2-fundament (icke-exekverande)** | **CONDITIONAL GO** | Capability-kontrakt, datamodeller, dry-run, eval-infra — under förutsättning att inget aktiverar decisioning-beroende execution |
| **Fas 2-fundament (decisioning-beroende flöden)** | **NO-GO** | Schema mismatch AI ↔ policy ej löst |
| **Fas 2 externa automatiska handlingar** | **NO-GO** | `create_monday_item` + `full_auto` utan action-approval; decisioning-seam |

### Sammanfattning för ledning

Kärnintelligensen **fungerar** för deterministisk, approval-first receptionist-driftsättning med keyword-risk. **AI decisioning är inte en tillförlitlig authorization-källa** i nuvarande kod. **Monday/CRM-skrivningar** kan ske utan mänsklig action-level gate när policy når `auto_execute`. Observability räcker för debugging men **inte för reproducerbarhet eller regulatorisk förklaring**. Nästa steg: låsa DecisionRecord-kontrakt (2B), bygga harness (2C), fixa decisioning-schema med regression (blockerande för execution-beroende Fas 2-arbete).

---

*Audit genomförd enligt Kapitel 2A-uppdrag. Subagent-rapporter verifierades av huvudagent mot källkod. Working tree oförändrad.*
