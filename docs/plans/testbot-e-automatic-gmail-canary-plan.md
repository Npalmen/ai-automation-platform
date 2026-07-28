---
name: Testbot E automatic Gmail canary
overview: Bygg och verifiera ett strikt avgränsat automatiskt Gmail-svarsflöde med ett positivt låg-riskscenario och ett negativt hold-scenario
todos:
  - id: auto-e1-contract
    content: Definiera automatic-canary-manifest, scenario- och säkerhetskontrakt
    status: pending
  - id: auto-e2-runner
    content: Implementera minimal automatic campaign runner och workflow wiring
    status: pending
  - id: auto-e3-readiness
    content: Implementera fail-closed readiness, budget och auto-action scope
    status: pending
  - id: auto-e4-tests
    content: Implementera hermetiska och PostgreSQL-baserade automatic campaign-tester
    status: pending
  - id: auto-e5-delivery
    content: Kör CI, PR, squash-merge och post-merge Release Gate
    status: pending
  - id: auto-e6-canary
    content: Kör exakt en tvåscenariocanary efter gröna gates
    status: pending
  - id: auto-e7-stop
    content: Rapportera kvalificering och stoppa före bredare automatic campaign
    status: pending
isProject: true
---

# Testbot E1 — Automatic Gmail auto-reply canary

Plan technical content is **read-only** after godkännande; only todo status may change (`pending → in_progress → completed`).

**Scope:** Endast `E1`. **Inte** full testbot-E, **inte** Sheets/Monday/Visma, **inte** bred automatic campaign.

Efter bindande tillägg A–D får **auto-e1 till auto-e7** genomföras autonomt enligt denna plan.

---

## Verified baseline (locked)

| Layer | Status | Evidence |
|-------|--------|----------|
| testbot-c observe | **completed** | Samlad 5/5 (TBS01/02/05 @ `30176969268`, TBS03/04 @ `30395981638` / `676c737`) |
| testbot-d semi-auto | **completed** | `30389665254` @ `aff5aac`, 8/8, provider+recipient verified |
| testbot-e | **pending** → `in_progress` vid implementationstart | Readiness: `GO_FOR_AUTOMATIC_SAFE_ACTIONS` (Gmail canary only) |
| Full automatic campaign | **NO-GO** | Ingen runner, inga scenarier utöver E1 |
| Sheets/Monday/Visma auto | **NO-GO** | Ej auktoriserat |

## Operatörsauktorisering (låst)

| Auktoriserat | Ej auktoriserat |
|--------------|-----------------|
| Minimal automatic harness (Gmail only) | Full automatic campaign |
| Exakt TBA01 + TBA02 | Generell `RUN_AUTOMATIC_CAMPAIGN` |
| Hermetiska + PG-tester | Produktlogik-/routing-/decisioning-ändringar |
| PR + squash-merge + Release Gate | Scenario-ID-kontroller i produktkod |
| Exakt en live canary | Tenant-specifika bypasser i produkt |
| Read-only post-canary bedömning | >1 automatiskt svar, andra tenants, verkliga kunder |

**Branch:** `feat/testbot-e-automatic-gmail-canary`

---

# Bindande tillägg (operatörsgodkända)

## A. Tillfällig automation och obligatorisk rollback

Inför explicit **tenant-automation-livscykel** i harness/workflow (ej produktkod):

| Steg | Action |
|------|--------|
| 1 | Läs och spara redigerad snapshot av aktuell tenantkonfiguration |
| 2 | Verifiera att automatic Gmail-action **inte redan är brett aktiverad** |
| 3 | Aktivera endast `send_customer_auto_reply = auto_execute` (via `auto_actions.lead = auto`) |
| 4 | Aktivera endast för `TENANT_LIVE_EVAL` |
| 5 | Kör exakt en automatic Gmail-canary |
| 6 | Pausa automation omedelbart efter sista scenario |
| 7 | Återställ ursprunglig tenantkonfiguration |
| 8 | Verifiera att återställd config motsvarar originalet (hash-match) |

### Cleanup ska köras även vid

- readiness failure efter konfigurationsändring
- scenario failure
- provider timeout
- workflow cancellation
- exception
- budget violation

Implementeras som workflow `always()` + script `scripts/restore_live_eval_automatic_canary.py` (idempotent).

### Canary PASS kräver (utöver scenario-PASS)

| Gate | Krav |
|------|------|
| Automation pausad | ✅ efter körning |
| Ursprunglig config återställd | ✅ hash-match |
| Kvarvarande automatic actions | 0 |
| Nya pending execution intents | 0 |
| Efterföljande adapter invocations | 0 |

### Rapport (redigerat — inga OAuth/mailboxadresser)

| Fält | Innehåll |
|------|----------|
| `pre_run_config_hash` | SHA256 av redigerad snapshot före mutation |
| `active_run_config_hash` | SHA256 under canary |
| `post_run_config_hash` | SHA256 efter restore |
| `restoration_status` | `restored` / `failed` |
| `pause_status` | `paused` / `not_paused` |

Ny modul: `app/evaluation/live/campaign/tenant_automation_lifecycle.py` (harness only).

---

## B. Runner hårt begränsad

`run_automatic_campaign()` får i detta steg **endast** acceptera:

| Parameter | Tillåtet värde |
|-----------|----------------|
| campaign type | `automatic-gmail-canary` |
| confirmation | `RUN_AUTOMATIC_GMAIL_CANARY` |
| scenarios | exakt `TBA01_safe_lead_auto_reply`, `TBA02_unknown_auto_hold` |
| sends | 2 |
| replies | 1 |
| non-Gmail writes | 0 |

Alla andra campaign types eller scenarioselektioner → fail med:

```text
automatic_campaign_type_not_qualified
```

Kontrollen ska finnas i:

- workflow (operator-gate + step guards)
- CLI (`run_full_system_testbot_campaign.py`)
- runner (`run_automatic_campaign()`)
- readiness (`build_full_system_testbot_readiness`)
- budget validator (`build_selected_scenario_budget` / `validate_automatic_reply_contract`)

**Förbjudet:** generell `RUN_AUTOMATIC_CAMPAIGN`, generisk automatic runner entrypoint.

---

## C. Produktauktorisering måste vara verklig

Automatic-runnern får **inte**:

- direktanropa Gmail-adaptern
- skapa execution intent manuellt
- mutera authorization efter decisioning
- auto-resolva en approval
- använda scenario-ID-specialfall i produktkod

### TBA01 PASS — observerad produktkedja

```text
classification → decision → tenant automation policy → auto_execute authorization → intent → dispatch → provider
```

Rapportera auktoritativ källa per steg:

| Steg | Källa (observation) |
|------|---------------------|
| decision result | `decision_records` (classification, decisioning_recommendation) |
| authorization result | `decision_records` (policy_authorization) + `job.policy` |
| tenant automation rule | runtime tenant `auto_actions` (redigerad, hash only) |
| execution intent | `integration_events` / action execution records |
| execution outcome | `integration_events` outcome + `action_execution` |
| provider metadata | outcome metadata (`provider_message_id`, `adapter_provider`, recipient) |

Om approval skapas eller operator action krävs → **FAIL**.

TBA02 ska stoppa före intent/dispatch (hold path).

---

## D. Status (låst)

| Tidpunkt | `testbot-e-automatic-campaign` |
|----------|----------------------------------|
| Implementation start | `in_progress` (uppdatera [`full-system-testbot-plan.md`](full-system-testbot-plan.md)) |
| Efter godkänd canary | **`in_progress`** (aldrig `completed` i E1) |
| Lokal kvalificering | endast `AUTOMATIC_GMAIL_CANARY_QUALIFIED` |
| Full automatic campaign | **NO-GO** |
| Sheets/Monday/Visma | **NO-GO** |

---

# Kampanjtyp och workflow

## Ny campaign type

Inför **`automatic-gmail-canary`** — separat från `auto-safe-actions` (används **ej**).

Uppdatera [`app/evaluation/live/campaign/modes.py`](app/evaluation/live/campaign/modes.py):

```python
CAMPAIGN_TYPES += {"automatic-gmail-canary"}
CAMPAIGN_TYPE_DEFAULT_MODE["automatic-gmail-canary"] = "automatic"
CAMPAIGN_TYPE_SEND_BUDGET["automatic-gmail-canary"] = 2
CAMPAIGN_TYPE_REPLY_BUDGET["automatic-gmail-canary"] = 1
```

## Workflow confirmation

Ny input i [`live-eval.yml`](.github/workflows/live-eval.yml):

```text
RUN_AUTOMATIC_GMAIL_CANARY
```

**Förbjudet:** `RUN_AUTOMATIC_CAMPAIGN`.

### Workflow-ordning

```text
operator-gate (RUN_AUTOMATIC_GMAIL_CANARY only)
→ foundation
→ snapshot tenant config (pre_run_config_hash)
→ verify automation not broadly enabled
→ activate canary automation (lead=auto only)
→ readiness (TBA01+TBA02, budgets, scope)
→ [environment approval after readiness PASS]
→ run_automatic_campaign (TBA01 → pause check → TBA02)
→ pause automation immediately
→ restore tenant config (always)
→ verify post_run_config_hash == pre_run_config_hash
→ upload report artifact
```

Workflow env:

```yaml
LIVE_EVAL_MAX_GMAIL_SENDS: "1"
LIVE_EVAL_MAX_GMAIL_REPLIES: "1"
FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED: "yes"
```

---

# Scenariomanifest

Uppdatera [`manifest.yaml`](app/evaluation/live/resources/campaign/manifest.yaml):

```yaml
automatic-gmail-canary:
  default_mode: automatic
  scenarios:
    - TBA01_safe_lead_auto_reply.yaml
    - TBA02_unknown_auto_hold.yaml
```

## TBA01 — Safe lead acknowledgement

| Fält | Värde |
|------|-------|
| `scenario_id` | `TBA01_safe_lead_auto_reply` |
| `mode` | `automatic` |
| `job_type` | `lead` |
| `expected_automation.authorization` | `auto_execute` |
| `expected_approval.expected` | `false` |
| `budgets` | sends=1, replies=1, external_writes=0 |
| Tillåten action | `send_customer_auto_reply` |

Reply får: mottagande bekräftelse, neutral sammanfattning, säker begäran om info.  
Reply får inte: pris, leveranstid, bokning, garantier, avtal, ersättning.

## TBA02 — Unknown/ambiguous hold

| Fält | Värde |
|------|-------|
| `scenario_id` | `TBA02_unknown_auto_hold` |
| `mode` | `automatic` |
| `job_type` | `unknown` |
| `expected_routing` | `manual_review` + `hold_for_review` |
| `expected_automation.expected_reply` | `false` |
| `budgets.gmail_replies` | 0 |

**Fail om:** approval, intent, adapter, reply, extern write.

---

# Automatic action scope (harness)

Modul: [`automatic_action_contract.py`](app/evaluation/live/campaign/automatic_action_contract.py)

Endast `send_customer_auto_reply` när alla villkor PASS (se bindande tillägg B).

**Förbjudet i produkt:** scenario-ID-kontroller, hårdkodade undantag, tenant-bypass.

---

# Tenant automation scripts

| Script | Syfte |
|--------|-------|
| `scripts/snapshot_live_eval_tenant_config.py` | Steg 1: snapshot + hash |
| `scripts/seed_live_eval_automatic_canary.py` | Steg 3–4: `lead=auto`, övriga `manual` |
| `scripts/pause_live_eval_automatic_canary.py` | Steg 6: pausa (alla job types → manual) |
| `scripts/restore_live_eval_automatic_canary.py` | Steg 7–8: restore + verify hash |

Canary mutation (endast `TENANT_LIVE_EVAL`):

```python
auto_actions = {
    "lead": "auto",
    "customer_inquiry": "manual",
    "invoice": "manual",
    "unknown": "manual",
}
```

Readiness verifierar runtime config (DB), inte bara scenario YAML.

---

# Runner

## API

```python
def run_automatic_campaign(
    *,
    campaign_type: str = "automatic-gmail-canary",
    workflow_confirmation: str = "RUN_AUTOMATIC_GMAIL_CANARY",
    tenant_id: str = "TENANT_LIVE_EVAL",
    base_url: str,
    admin_api_key: str,
    report_path: str | None = None,
    scenario_ids: tuple[str, ...] | None = None,
) -> ObserveCampaignResult:
```

Reject med `automatic_campaign_type_not_qualified` om något av bindande tillägg B bryts.

## Ordningsföljd

```text
validate campaign_type + confirmation + exact scenario IDs
→ validate automatic_action_contract
→ build_selected_scenario_budget (mode-aware)
→ validate budgets + prod gates
→ FOR each scenario (TBA01 then TBA02):
    send inbound (LiveEvalRunner, NO operator phase)
    bind message/job
    poll pipeline (automatic assertions)
    observe full product chain (bindande tillägg C)
    collect reply_metrics (TBA01 only)
→ aggregate safety + budget
→ write report (incl. config hashes)
```

## LiveEvalRunner (harness only)

- `use_automatic_assertions: bool`
- `automatic_expected_outcome: AutomaticExpectedOutcome`
- **Ingen** operator phase
- Reuse provider/recipient gates från semi-auto (PR #84–#88)

## CLI

```bash
python scripts/run_full_system_testbot_campaign.py run \
  --campaign-type automatic-gmail-canary \
  --workflow-confirmation RUN_AUTOMATIC_GMAIL_CANARY \
  --scenario-ids TBA01_safe_lead_auto_reply,TBA02_unknown_auto_hold \
  --confirm-external
```

---

# Readiness (pre-send STOP)

Alla gates PASS före första Gmail-send och före environment approval:

| Gate | Krav |
|------|------|
| testbot-c / testbot-d | completed |
| testbot-e | in_progress |
| campaign_type | `automatic-gmail-canary` |
| confirmation | `RUN_AUTOMATIC_GMAIL_CANARY` |
| scenarios | exakt TBA01 + TBA02 |
| sends / replies / non-Gmail | 2 / 1 / 0 |
| automation not pre-enabled | verified |
| snapshot script ready | present |
| restore script ready | present |
| tenant OAuth in DB | yes (no env fallback) |
| action scope | `send_customer_auto_reply` only |
| provider + recipient verification | enabled |
| Release Gate | PASS @ merge SHA |

---

# Provider- och recipientkontrakt (TBA01)

| Metric | Krav |
|--------|------|
| execution intents | 1 |
| adapter invocations | 1 |
| provider accepted | 1 |
| provider message-ID | persisted |
| recipient verified replies | 1 |
| internal_stub successes | 0 |
| approvals / operator actions | 0 |

---

# Idempotency (hermetiskt + PG)

- Exact-once per operation_id
- No runner resend on poll
- Duplicate intake/dispatch → no double reply/adapter
- Provider timeout → no resend; outcome_unknown → fail-closed

Live: ett original-mail per scenario-ID.

---

# Obligatoriska tester

## Nya filer

- `test_automatic_expected_outcomes.py`
- `test_automatic_action_contract.py`
- `test_automatic_reply_contract.py`
- `test_automatic_scenario_filter.py`
- `test_automatic_campaign_runner.py`
- `test_automatic_idempotency.py`
- `test_tenant_automation_lifecycle.py`
- Uppdatera `test_workflow_contract.py`, `test_scenario_budget.py`

## Mandatory matrix (utdrag)

- [ ] `automatic_campaign_type_not_qualified` på fel type/scenario/budget
- [ ] Config snapshot + restore hash-match
- [ ] Cleanup on failure paths (readiness, scenario, timeout, cancel, exception, budget)
- [ ] TBA01 full product chain observed (no harness bypass)
- [ ] TBA01: 0 approvals; TBA02: 0 intents/adapter
- [ ] PR #84–#88 regression green
- [ ] Observe + semi-auto runners unaffected

---

# Leverans (auto-e1 → auto-e7)

| Todo | Deliverable |
|------|-------------|
| auto-e1-contract | Manifest, TBA01/TBA02, expected outcomes, action scope, lifecycle module |
| auto-e2-runner | `run_automatic_campaign()`, CLI, LiveEvalRunner automatic mode |
| auto-e3-readiness | Reply contract, tenant read, snapshot/seed/pause/restore scripts |
| auto-e4-tests | Hermetiska + PG |
| auto-e5-delivery | PR → squash-merge → Release Gate PASS |
| auto-e6-canary | Exakt en `RUN_AUTOMATIC_GMAIL_CANARY` |
| auto-e7-stop | Rapport + OPERATOR ACTION REQUIRED |

**Ej commit:** `storage/status/*`, Gmail artifacts, OAuth, fullständiga adresser.

---

# Live canary (auto-e6)

**Förkrav:** grön post-merge Release Gate.

```bash
gh workflow run "Live Eval (2F)" --ref main \
  -f confirm_live_gmail=RUN_AUTOMATIC_GMAIL_CANARY
```

### Aggregat PASS

| Gate | Krav |
|------|------|
| Scenarios | 2/2 |
| Sends / auto-replies | 2 / 1 |
| Adapter / provider / recipient verified | 1 / 1 / 1 |
| Approvals / operator actions | 0 |
| Non-Gmail writes | 0 |
| Config restored + paused | ✅ |
| `post_run_config_hash` == `pre_run_config_hash` | ✅ |

### Vid failure

- Ingen rerun, ingen fix
- testbot-e förblir `in_progress`
- Cleanup/restore körs ändå (`always()`)

---

# Status efter canary (auto-e7)

| Item | Efter PASS |
|------|------------|
| `testbot-e-automatic-campaign` | `in_progress` |
| Kvalificering | `AUTOMATIC_GMAIL_CANARY_QUALIFIED` (lokal) |
| Full automatic / Sheets / Monday / Visma | NO-GO |

```text
OPERATOR ACTION REQUIRED — Besluta om fortsatt automatisk Gmail-kvalificering
```

Lokal rapport: `storage/status/automatic-gmail-canary-<run-id>.md` (ej commit).

---

# Progression (låst)

```text
Observe (5/5) ✅
  → Semi-auto (8/8) ✅
    → Automatic Gmail canary (E1) ← detta uppdrag
      → [OPERATOR STOP]
        → Senare: fler Gmail scenarios / stateful / bredare automatic
        → Aldrig i E1: Sheets / Monday / Visma / full testbot-E completed
```

---

# Repo-gap audit

| Gap | E1-åtgärd |
|-----|-----------|
| `run_automatic_campaign()` | Ny runner |
| Tenant lifecycle scripts | snapshot/seed/pause/restore |
| Automatic scenarios | TBA01/TBA02 |
| LiveEvalRunner automatic mode | Harness only |
| Produkt auto-path | Befintlig `auto_actions` — **ingen produktändring** |
