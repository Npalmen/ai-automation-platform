# Kapitel 2G — Repositoryaudit (2g-a-audit-contract)

**Datum:** 2026-07-25  
**Planversion:** `2g-execution-plan-v2`  
**Startbaseline:** `main @ 1d7073a433f901753449e57ec2ca2293ce56fbcf` ✓  
**2F-status:** PASS och stängt (artifact `2f-final-evidence-1d7073a…`, run `30165696034`)

---

## Startbaseline-verifiering

| Kontroll | Resultat |
|---|---|
| `origin/main` | `1d7073a433f901753449e57ec2ca2293ce56fbcf` ✓ |
| Post-merge Release Gate 2F | `30165696034`, success ✓ |
| 2F final report | `overall_status=passed` ✓ |
| Lokal WIP | Endast `storage/`, `docs/plans/` (ej committat) — ej blockerande |

---

## Auditområden

### Gold dataset och manifest — redan implementerad

| Artefakt | Sökväg | Status |
|---|---|---|
| Canonical scenarios (20) | `tests/evaluation/scenarios/S*.yaml` | ✅ |
| Manifest | `tests/evaluation/datasets/k2e-v1.yaml` | ✅ |
| Baseline | `tests/evaluation/baselines/k2e-baseline-v1.json` | ✅ |
| `manifest_hash` | `600e7fd601227d0e327951df8f2a91f48eb6af713410f2a76f819d4db5a793d8` | ✅ låst |
| `hash_algorithm` | `semantic-json-v2` | ✅ |
| Coverage gate | `app/evaluation/coverage.py` | ✅ |
| Harness runner | `app/evaluation/runner.py` | ✅ fixture-only |

### semantic-json-v2 — redan implementerad

- `app/evaluation/dataset_manifest.py`: `canonical_json_bytes()`, `HASH_ALGORITHM`, `compute_scenario_content_hash()`
- Återanvänds av 2F: `final_evidence.py`, `replay_verifier.py`

### Provenance schema — delvis implementerad

`GenerationContract` i `app/evaluation/schema/scenario.py` innehåller:

- `parent_scenario_id`, `template_id`, `seed`, `variation_id`
- `generator_model`, `generator_prompt_version`, `mutation_types`
- `source_mode` stöder `fixture|generated|live_gmail|replay`

**Saknas för 2G-planen (ska läggas i todo B, ej i gold):**

- `template_version`, `mutation_parameters`, `generator_type`, `generator_version`
- `expected_outcome_hash`, top-level `scenario_schema_version: "2g.scenario.v1"`

**Klassificering:** delvis implementerad — utöka i `app/evaluation/generation/` utan att ändra gold YAML.

### Evaluation runner — redan implementerad (fixture-only)

- `runner.py:135` — nekar `source_mode != "fixture"`
- Batch-runner för `generated` scenarios tillkommer i todo D (eller utökning av runner)

### Recorded-output replay — delvis implementerad

- 2F evidence replay: `app/evaluation/live/replay_verifier.py`, `scripts/run_2f_offline_replay.py` ✅
- Scenario LLM recorded-output replay för harness: ❌ saknas (plan tillåter endast befintligt säkert stöd — använd `fixture_ai`)

### Report builders, redaction, no-network — redan implementerad (2F-mönster)

- Redaction: `app/evaluation/live/redaction.py`, `provider_redaction.py`
- No-network-tester: `tests/evaluation/live/test_2f_replay.py`, `test_2f_closure.py`
- 2G-rapporter: ❌ saknas (todo D/E)

### Release Gate — redan implementerad (2F, ej 2G)

`.github/workflows/release-gate.yml`:

| Jobb | Status |
|---|---|
| tests | ✅ |
| live-eval-postgres | ✅ |
| frontend | ✅ |
| docker | ✅ |
| final-2f-evidence | ✅ push main |
| 2g-pr-eval | ❌ saknas (todo E) |
| 2g-main-eval | ❌ saknas (todo E) |
| final-2g-evidence | ❌ saknas (todo E) |

### Generation / mutation / batch — saknas

| Modul | Status |
|---|---|
| `app/evaluation/generation/` | ❌ |
| `app/evaluation/mutations/` | ❌ |
| `app/evaluation/batch/` | ❌ |
| `tests/fixtures/2g/` | ❌ |
| `scripts/generate_2g_scenarios.py` | ❌ |
| `scripts/run_2g_batch.py` | ❌ |

Legacy `scripts/generate_eval_scenarios.py` (2D-era, 8 scenarios) — **ej 2G**, används inte.

---

## Kontraktsklassificering

| Komponent | Klassificering |
|---|---|
| 20 canonical gold scenarios | redan implementerad |
| Manifest + baseline + smoke CI | redan implementerad |
| semantic-json-v2 | redan implementerad |
| GenerationContract (bas) | delvis implementerad |
| 2F evidence/closure | redan implementerad |
| Template/seed generator | dokumenterad men ej implementerad |
| Mutation engine | saknas |
| 60/160 batch evaluation | saknas |
| 2G CI jobs + closure artifact | saknas |

### Identifierade avvikelser (ej stop-gates)

| # | Avvikelse | Åtgärd |
|---|---|---|
| 1 | Runner fixture-only | Utöka i todo D via batch-runner |
| 2 | Plan `2g.scenario.v1` vs gold `2e.1` | Gold oförändrat; 2G-version i generation manifest |
| 3 | Extra provenance-fält | Lägg till i `generation/provenance.py` (todo B) |
| 4 | Backlog nämner AI-generering | Plan vinner: template-baserad, ingen AI |

**Inga kontraktskonflikter som blockerar implementation.**

---

## Fortsättningsgate — PASS

| Krav | Resultat |
|---|---|
| Canonical IDs och hashes stabila | ✅ |
| semantic-json-v2 återanvändbar | ✅ |
| Generator/mutations passar i evalstruktur | ✅ |
| Ingen migration krävs | ✅ |
| Inget externt anrop krävs | ✅ |
| Inga låsta kontrakt behöver ändras | ✅ |

**Beslut:** Fortsätt till `2g-b-generator-provenance`. Ingen commit/PR för auditsteget.

---

## Verifierat filscope per todo

### B — `feat/2gb-deterministic-generator`

```
app/evaluation/generation/
scripts/generate_2g_scenarios.py
tests/evaluation/generation/
tests/fixtures/2g/
```

### C — `feat/2gc-mutation-engine`

```
app/evaluation/generation/ (utökning)
app/evaluation/mutations/
tests/evaluation/mutations/
tests/fixtures/2g/
```

### D — `feat/2gd-batch-quality-gates`

```
app/evaluation/batch/
app/evaluation/reports/ (om behövs)
scripts/run_2g_batch.py
tests/evaluation/batch/
```

### E — `feat/2ge-close-2g`

```
app/evaluation/closure_2g.py (eller generation/closure)
scripts/run_2g_offline_closure.py
.github/workflows/release-gate.yml (utökning)
tests/evaluation/test_2g_closure.py
docs/01-current-truth.md, 06-backlog.md, 09-testing-and-release.md
```

**Får ej ändras:** `tests/evaluation/scenarios/*.yaml`, `k2e-v1.yaml`, baseline, canonical hashes.
