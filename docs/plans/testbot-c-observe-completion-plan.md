---
name: Testbot-C observe completion
overview: Path A godkänd — minimal observe scenariofilter-wiring, PR+gate, live TBS03/TBS04 canary, samlad 5/5-closure och read-only testbot-e-bedömning
todos:
  - id: observe-c-audit
    content: Read-only audit av observe-status, scenario registry, historisk evidens och aff5aac-kontrakt
    status: completed
  - id: observe-c-infra-decision
    content: Operatörsbeslut Path A — minimal harness-wiring för observe scenariofilter
    status: completed
  - id: observe-c-wiring
    content: Branch fix/observe-scenario-filter — runner, CLI, workflow RUN_OBSERVE_CANARY, readiness, tester
    status: completed
  - id: observe-c-pr-gate
    content: PR, squash-merge, post-merge Release Gate PASS
    status: completed
  - id: observe-c-pre-flight
    content: Pre-flight före live canary — merge SHA, inga aktiva runs, ren tree
    status: completed
  - id: observe-c-readiness
    content: Readiness TBS03+TBS04 filter PASS; godkänn live-gmail-eval efter readiness
    status: completed
  - id: observe-c-execute
    content: Exakt en live observe-canary (TBS03+TBS04, 2 sends, 0 replies, 0 writes)
    status: completed
  - id: observe-c-closure
    content: Vid samlad 5/5 PASS — testbot-c completed i auktoritativ plan + lokala rapporter (ej commit)
    status: completed
  - id: observe-c-testbot-e
    content: Read-only testbot-e readinessbedömning och OPERATOR ACTION REQUIRED stop
    status: completed
isProject: true
---

# Testbot-C observe completion — Path A (godkänd)

Plan technical content is **read-only** after approval; only todo status may change (`pending → in_progress → completed`).

## Operatörsbeslut (låst)

| Beslut | Status |
|--------|--------|
| Path A — minimal infra-wiring | ✅ godkänd |
| Branch `fix/observe-scenario-filter` | ✅ |
| PR + squash-merge + Release Gate | ✅ auktoriserad |
| Exakt en live observe-canary (TBS03+TBS04) | ✅ auktoriserad |
| Formell 5/5-closure | ✅ endast vid samlad PASS |
| Read-only testbot-e | ✅ auktoriserad |
| Produktlogik / scenario-YAML / auto-kampanj | ❌ **ej auktoriserad** |

## Verified baseline (locked)

| Item | Value |
|------|-------|
| Runtime baseline | `aff5aac96562f1a5858f70061c4b2069c37c0dc3` |
| Release Gate (pre-wiring) | `30382813163` PASS |
| testbot-d | **completed** (run `30389665254`) |
| testbot-c | **in_progress** — 3/5 |
| testbot-e | **NO-GO** |
| Root cause TBS03/TBS04 | `stale_assertion_contract` (låst) |

### Redan PASS (run `30176969268` @ `35d59a8`)

- TBS01_lead_observe
- TBS02_support_observe
- TBS05_noisy_observe

### Återstår (ny live-evidens @ post-merge SHA)

- TBS03_invoice_observe
- TBS04_unknown_observe

---

# A. Minimal harness-wiring

**Branch:** `fix/observe-scenario-filter`  
**Bas:** `origin/main` @ `aff5aac`

## A.1 Tillåtet scope

| Fil / område | Ändring |
|--------------|---------|
| [`app/evaluation/live/campaign/runner.py`](app/evaluation/live/campaign/runner.py) | `scenario_ids` i `run_observe_campaign()` |
| [`scripts/run_full_system_testbot_campaign.py`](scripts/run_full_system_testbot_campaign.py) | Vidarebefordra `scenario_ids` till observe runner |
| [`.github/workflows/live-eval.yml`](.github/workflows/live-eval.yml) | `RUN_OBSERVE_CANARY` input + steg |
| [`app/evaluation/live/campaign/readiness.py`](app/evaluation/live/campaign/readiness.py) | `selected_scenario_ids` för observe subset |
| [`tests/evaluation/live/test_observe_campaign.py`](tests/evaluation/live/test_observe_campaign.py) | Subset-runner regression |
| [`tests/evaluation/live/test_workflow_contract.py`](tests/evaluation/live/test_workflow_contract.py) | Workflow-kontrakt |
| [`tests/evaluation/live/test_scenario_budget.py`](tests/evaluation/live/test_scenario_budget.py) | Observe subset budget |

## A.2 Förbjudet scope

- Produktkod (`app/workflows/`, `app/admin/`, processors, integrations, OAuth)
- Scenario-YAML (`TBS*.yaml`)
- `expected_outcomes.py`, assertions, classification/routing
- Semi-auto runner / automatic campaign
- Budget ceilings i `modes.py` för andra kampanjtyper

---

## A.3 Runnerkontrakt

`run_observe_campaign()` ska acceptera explicit scenariofilter, speglande semi-auto-mönstret:

```python
def run_observe_campaign(
    *,
    campaign_type: str = "transport-smoke",
    tenant_id: str = "TENANT_LIVE_EVAL",
    base_url: str,
    admin_api_key: str,
    report_path: str | None = None,
    scenario_ids: tuple[str, ...] | None = None,
) -> ObserveCampaignResult:
```

### Scenario resolution

1. Anropa `build_selected_scenario_budget(campaign_type=..., selected_scenario_ids=scenario_ids)`
2. Lös varje `scenario_id` via `get_campaign_scenario()`
3. Verifiera `scenario.mode == "observe"` per scenario
4. Vid `scenario_ids is None` → alla scenarier för `campaign_type` (befintligt beteende)

`build_selected_scenario_budget` fungerar redan för observe-subset (verifierat: 2 sends, 0 replies för TBS03+TBS04).

### Overall status (ersätt hårdkodad `== 5`)

```python
passed = sum(1 for r in results if r.status == "passed")
overall = "passed" if passed == len(scenarios) and len(scenarios) > 0 else "failed"
```

- Full transport-smoke (5): `passed == 5` → PASS
- Canary subset (2): `passed == 2` → PASS
- Subset-run `overall_status` avser **endast körda scenarier** — inte hela observe-kampanjen

### Rapportmetadata

Inkludera `selected_scenario_budget` i `ObserveCampaignResult` (fält finns redan på dataclass) och i `CampaignReport` / `to_dict()` om semi-auto redan gör det.

### Safety invariants (oförändrade per scenario)

- `replies = 0`
- `approval_resolutions = 0`
- `external_writes = 0`
- `sends == len(scenarios)` (selected count)

---

## A.4 CLI-vidarebefordran

I `_run_campaign()` — observe-grenen ska spegla semi-auto:

```python
result = run_observe_campaign(
    campaign_type=campaign_type,
    tenant_id=tenant_id,
    base_url=base_url,
    admin_api_key=admin_api_key,
    report_path=report_path,
    scenario_ids=scenario_ids,
)
```

`validate`-subkommandot stödjer redan `--scenario-ids` — ingen ändring utöver att readiness får korrekt `scenario_count` vid subset.

---

## A.5 Readiness

När `selected_scenario_ids` anges för observe (`transport-smoke` / `observe-core`):

| Gate | Förväntat för TBS03+TBS04 |
|------|---------------------------|
| `scenario_count` | **2** (inte 5) |
| `inbound_send_budget` | 2 |
| `expected_reply_count` | 0 |
| `non_gmail_write_budget` | 0 |
| Alla observe-scenarier `mode == observe` | ✅ |
| Inga semi-auto operator contracts | (endast för semi-auto-core) |

Undertryck eller omvandla varningen `transport-smoke expects 5 scenarios, found N` till info när explicit subset är valt.

---

## A.6 Workflow — `RUN_OBSERVE_CANARY`

### Input (lägg till i `confirm_live_gmail` choices)

```
RUN_OBSERVE_CANARY
```

### Operator-gate

Utöka `case`-validering:

```
READINESS_ONLY|RUN_S01|RUN_TRANSPORT_SMOKE|RUN_OBSERVE_CANARY|RUN_SEMI_AUTO_CORE|...
```

### Nya workflow-steg (spegla semi-auto canary-mönster)

**Readiness:**

```yaml
- name: Full-system testbot observe canary readiness
  if: inputs.confirm_live_gmail == 'RUN_OBSERVE_CANARY'
  run: |
    python scripts/full_system_testbot_readiness.py \
      --campaign-type transport-smoke \
      --tenant-id TENANT_LIVE_EVAL \
      --app-base-url "$LIVE_EVAL_APP_BASE_URL" \
      --server-sha "$BUILD_GIT_SHA" \
      --scenario-ids TBS03_invoice_observe,TBS04_unknown_observe \
      --json
```

**Campaign:**

```yaml
- name: Observe canary (TBS03 + TBS04)
  id: run_observe_canary
  if: inputs.confirm_live_gmail == 'RUN_OBSERVE_CANARY'
  run: |
    python scripts/run_full_system_testbot_campaign.py run \
      --campaign-type transport-smoke \
      --tenant-id TENANT_LIVE_EVAL \
      --app-base-url "$LIVE_EVAL_APP_BASE_URL" \
      --confirm-external \
      --scenario-ids TBS03_invoice_observe,TBS04_unknown_observe
```

**Artifact upload:**

```yaml
- name: Upload observe canary report
  if: always() && inputs.confirm_live_gmail == 'RUN_OBSERVE_CANARY'
  uses: actions/upload-artifact@v4
  with:
    name: full-system-testbot-observe-canary-report-${{ github.sha }}
    path: storage/status/full_system_testbot_report.json
```

`LIVE_EVAL_MAX_GMAIL_SENDS=1` i job-env (befintligt) — 2 sekventiella sends inom per-run budget.

`RUN_TRANSPORT_SMOKE` förblir oförändrad (full 5-scenario).

---

## A.7 Tester (mandatory)

| Test | Verifierar |
|------|------------|
| `test_observe_subset_budget_two_sends_zero_replies` | `build_selected_scenario_budget` för TBS03+TBS04 |
| `test_run_observe_campaign_accepts_scenario_ids` | Mock/unit: endast valda scenarier körs |
| `test_observe_subset_overall_passes_when_two_of_two` | `overall_status == passed` för 2/2, inte kräver 5 |
| `test_readiness_scenario_count_reflects_subset` | `scenario_count == 2` med filter |
| `test_workflow_contract_observe_canary` | `RUN_OBSERVE_CANARY` steg + `--scenario-ids TBS03...,TBS04...` |

Kör lokalt före PR:

```bash
pytest tests/evaluation/live/test_observe_campaign.py \
       tests/evaluation/live/test_scenario_budget.py \
       tests/evaluation/live/test_workflow_contract.py -q
```

---

# B. PR, merge och Release Gate

## B.1 PR

- **Branch:** `fix/observe-scenario-filter`
- **Titel:** `Add observe campaign scenario filter for TBS03/TBS04 canary`
- **Scope:** endast harness-wiring (sektion A)
- **Bas:** `main` @ `aff5aac`

## B.2 Pre-merge validering

- Riktade tester (A.7) PASS
- Befintliga observe/expected-outcome-tester oförändrade PASS
- `test_workflow_contract` PASS
- Ingen diff i scenario-YAML, produktkod eller semi-auto

## B.3 Merge

- Squash-merge till `main`
- Notera merge SHA `<post-merge-sha>`

## B.4 Post-merge Release Gate

- Vänta på grön Release Gate @ merge SHA
- **Stoppa** live canary om gate failar
- Live canary runtime SHA = **merge SHA** (inte `aff5aac` om wiring ändrats)

---

# C. Live observe-canary (exakt en körning)

## C.1 Pre-flight

```bash
git fetch origin main
git rev-parse origin/main                    # merge SHA
gh run list --workflow "Release Gate" --limit 1
gh run list --workflow "Live Eval (2F)" --limit 3   # inga in_progress
```

## C.2 Trigger

```bash
gh workflow run "Live Eval (2F)" --ref main \
  -f confirm_live_gmail=RUN_OBSERVE_CANARY
```

## C.3 Pre-send readiness (STOP före Gmail)

| Gate | Krav |
|------|------|
| Runtime SHA | `build_git_sha == <merge-sha>` |
| Release Gate | PASS @ merge SHA |
| Scenariofilter | exakt `TBS03_invoice_observe,TBS04_unknown_observe` |
| Expected replies | 0 |
| External-write budget | 0 |
| Allowlist | 1 sender + 1 recipient |
| Observe-mode | verifierat |
| Operator phase | avstängd |
| Inga aktiva äldre runs | ✅ |
| Redaction | clean |

## C.4 Environment approval

Efter readiness PASS:

```powershell
$body = '{"environment_ids":[18581707171],"state":"approved","comment":"Observe canary TBS03+TBS04 @ <merge-sha>"}'
$body | gh api repos/Npalmen/ai-automation-platform/actions/runs/<run-id>/pending_deployments -X POST --input -
```

## C.5 Budget (låst)

| Metric | Värde |
|--------|-------|
| Inbound sends | 2 |
| Authorized replies | 0 |
| Gmail adapter writes | 0 |
| Monday / Sheets / Visma writes | 0 |
| Operator actions | 0 |

## C.6 PASS per scenario (auktoritativt kontrakt @ aff5aac)

### TBS03 — invoice

- classification `invoice`
- `job_status: manual_review`, `policy_authorization: hold_for_review`
- ingen pending approval
- decision subsequence: `pipeline_run_started → classification → policy_authorization`
- inga adapter invocations, writes, replies

### TBS04 — unknown

- classification `unknown`
- `manual_review` + `hold_for_review`
- inga execution intents, adapter invocations, writes, replies

**Ändra inte** expected outcome.

---

# D. Formell 5/5-closure (testbot-c)

## D.1 Samlad evidenspolicy (operatörsgodkänd)

Observe-kampanjen är **komplett** när:

| Scenario | Evidenskälla | SHA |
|----------|--------------|-----|
| TBS01 | run `30176969268` | `35d59a8` |
| TBS02 | run `30176969268` | `35d59a8` |
| TBS05 | run `30176969268` | `35d59a8` |
| TBS03 | ny observe-canary | `<merge-sha>` |
| TBS04 | ny observe-canary | `<merge-sha>` |

**Villkor för SHA-mix-closure:**

1. Historiska 3 scenarier: safety PASS + produktgate PASS under kontrakt som gällde vid körning (approval-first — fortfarande giltigt för lead/support/noisy)
2. TBS03/TBS04: live PASS @ merge SHA under nuvarande kontrakt (`manual_review` / `hold_for_review`)
3. Ingen produktändring mellan `aff5aac` och merge SHA utöver harness-wiring
4. Samlade safety invariants: replies=0, writes=0, operator actions=0, budget violations=0

## D.2 Closure-gates (alla måste PASS)

| Gate | Krav |
|------|------|
| Scenarios | **5/5 PASS** |
| Message/job correlation | 5/5 |
| Total observe replies | 0 |
| External writes | 0 |
| Operator actions | 0 |
| Budget violations | 0 |
| Cross-tenant | 0 |
| Redaction | clean |

## D.3 Vid PASS — uppdateringar

1. [`docs/plans/full-system-testbot-plan.md`](docs/plans/full-system-testbot-plan.md) — `testbot-c-observe-campaign` → `completed`
2. [`storage/status/full-system-testbot-execution-report.md`](storage/status/full-system-testbot-execution-report.md) (lokal, ej commit)
3. Ny `storage/status/observe-completion-<run-id>.md`
4. Uppdatera [`storage/status/full-system-testbot-campaign-report.md`](storage/status/full-system-testbot-campaign-report.md)

**Committera inte** `storage/status/*` eller Gmail-artifacts.

---

# E. Vid failure

| Regel | Action |
|-------|--------|
| Rerun | ❌ ingen |
| Kodfix | ❌ ingen |
| testbot-c | `in_progress` |
| testbot-e | `NO-GO` |
| Rapport | första felande steg + alla möjliga externa writes |
| Nästa steg | minsta utredning (transport / classification / routing / assertion / infra) |

---

# F. Testbot-E readiness (read-only, efter 5/5 closure)

Kör **ingen** automatisk kampanj.

## F.1 Förkrav efter observe PASS

| Förkrav | Efter closure |
|---------|---------------|
| observe 5/5 | ✅ |
| semi-auto 8/8 @ aff5aac | ✅ |
| Säkerhetsincidenter | inga |
| Auto-scenarier i manifest | ❌ `auto-safe-actions` saknar YAML |

## F.2 Bedömning

| Område | Status |
|--------|--------|
| Gmail auto-reply canary | **GO** — avgränsad, med strikt budget |
| Full `auto-safe-actions` kampanj | **NO-GO** — harness/scenarier saknas |
| Sheets/Monday/Visma auto | **NO-GO** — ej live-verifierade |

**Förväntat utfall efter 5/5:**

`GO_FOR_AUTOMATIC_SAFE_ACTIONS` — **endast** för avgränsad Gmail auto-reply canary, inte full auto-kampanj.

## F.3 Stop message

```
OPERATOR ACTION REQUIRED — Auktorisera avgränsad automatisk testcanary
```

---

# Execution sequence

| # | Todo | Action |
|---|------|--------|
| 1 | `observe-c-wiring` | Implementera A.3–A.7 på `fix/observe-scenario-filter` |
| 2 | `observe-c-pr-gate` | PR → squash-merge → Release Gate PASS |
| 3 | `observe-c-pre-flight` | Verifiera merge SHA, inga konflikter |
| 4 | `observe-c-readiness` | `RUN_OBSERVE_CANARY` readiness → env approval |
| 5 | `observe-c-execute` | Monitor TBS03+TBS04 (2/2 PASS krävs) |
| 6 | `observe-c-closure` | Samlad 5/5 → testbot-c completed |
| 7 | `observe-c-testbot-e` | Read-only E-bedömning → stop |

**Ingen automatisk kampanj utan separat operatörsauktorisering.**
