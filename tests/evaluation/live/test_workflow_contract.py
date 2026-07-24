"""Workflow YAML contract tests."""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW_PATH = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "live-eval.yml"
FOUNDATION_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/ai_platform"


def _load_workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _workflow_trigger(data: dict) -> dict:
    return data.get("on") or data[True]


def _step_by_name(steps: list[dict], needle: str) -> dict:
    return next(step for step in steps if needle in (step.get("name") or ""))


def _step_index(steps: list[dict], needle: str) -> int:
    return next(i for i, step in enumerate(steps) if needle in (step.get("name") or ""))


def _foundation_db_env(step: dict) -> dict:
    return step.get("env") or {}


def test_foundation_postgres_bootstrap_contract():
    data = _load_workflow()
    foundation = data["jobs"]["foundation"]
    assert "environment" not in foundation

    job_env = foundation.get("env") or {}
    assert "DATABASE_URL" not in job_env
    assert "ENV" not in job_env
    assert "secrets" not in str(foundation)
    for secret_name in (
        "LIVE_EVAL_SENDER_GMAIL",
        "LIVE_EVAL_RECIPIENT_GMAIL",
        "LIVE_EVAL_ADMIN_API_KEY",
        "${{ secrets.",
    ):
        assert secret_name not in str(foundation.get("env") or {})

    steps = foundation["steps"]
    names = [step.get("name", "") for step in steps]

    health_idx = _step_index(steps, "PostgreSQL service healthy")
    bootstrap_idx = _step_index(steps, "Bootstrap PostgreSQL schema")
    collect_idx = _step_index(steps, "Verify integration_db test selection")
    integration_idx = _step_index(steps, "Run live-eval PostgreSQL integration_db tests")
    junit_idx = _step_index(steps, "Verify integration_db JUnit gate")
    hermetic_idx = _step_index(steps, "Run live-eval hermetic tests")
    validate_idx = _step_index(steps, "Validate config (offline)")
    dry_run_idx = _step_index(steps, "Offline dry-run")

    assert health_idx < bootstrap_idx < collect_idx < integration_idx < junit_idx < hermetic_idx < validate_idx < dry_run_idx

    bootstrap = steps[bootstrap_idx]
    assert bootstrap["run"].strip() == "python -m scripts.ci.bootstrap_postgres_schema"
    assert _foundation_db_env(bootstrap) == {
        "ENV": "test",
        "DATABASE_URL": FOUNDATION_DATABASE_URL,
    }

    collect = steps[collect_idx]
    collect_run = collect.get("run") or ""
    assert "--collect-only" in collect_run
    assert "tests/evaluation/live" in collect_run
    assert "-m integration_db" in collect_run
    assert '"11"' in collect_run or "!= \"11\"" in collect_run or '!= "11"' in collect_run
    assert "test_root_job_atomic_pg.py" in collect_run
    assert "test_telemetry_idempotency_pg.py" in collect_run
    assert "test_registry_refresh_pg.py" in collect_run
    assert "test_cleanup_persistence_pg.py" in collect_run
    assert _foundation_db_env(collect) == {
        "ENV": "test",
        "DATABASE_URL": FOUNDATION_DATABASE_URL,
    }

    integration = steps[integration_idx]
    integration_run = integration.get("run") or ""
    assert "foundation_integration_db.junit.xml" in integration_run
    assert "-m integration_db" in integration_run
    assert "tests/evaluation/live" in integration_run
    assert _foundation_db_env(integration) == {
        "ENV": "test",
        "DATABASE_URL": FOUNDATION_DATABASE_URL,
    }

    junit = steps[junit_idx]
    assert "verify_pytest_junit.py foundation_integration_db.junit.xml --expected 11" in (
        junit.get("run") or ""
    )
    assert "env" not in junit or junit.get("env") is None

    hermetic = steps[hermetic_idx]
    hermetic_env = hermetic.get("env") or {}
    assert "DATABASE_URL" not in hermetic_env
    assert "ENV" not in hermetic_env

    validate = steps[validate_idx]
    assert (validate.get("env") or {}) == {"ENV": "test"}
    assert "DATABASE_URL" not in (validate.get("env") or {})

    dry_run = steps[dry_run_idx]
    assert (dry_run.get("env") or {}) == {"ENV": "test"}
    assert "DATABASE_URL" not in (dry_run.get("env") or {})

    bootstrap_count = sum(
        1 for step in steps if "bootstrap_postgres_schema" in (step.get("run") or "")
    )
    assert bootstrap_count == 1


def test_live_eval_workflow_contract():
    data = _load_workflow()
    transport = data["jobs"]["live_gmail_transport"]
    assert transport["timeout-minutes"] == 45
    assert transport["environment"] == "live-gmail-eval"
    assert transport["needs"] == ["foundation", "operator-gate"]
    assert data["concurrency"]["group"] == "live-gmail-eval"
    assert data["concurrency"]["cancel-in-progress"] is False

    permissions = data.get("permissions") or {}
    assert permissions == {"contents": "read"}

    trigger = _workflow_trigger(data)
    dispatch = trigger["workflow_dispatch"]
    assert "push" not in trigger
    assert "pull_request" not in trigger
    assert "schedule" not in trigger

    confirm_input = dispatch["inputs"]["confirm_live_gmail"]
    assert confirm_input["required"] is True
    assert confirm_input["type"] == "choice"
    assert confirm_input["default"] == "DO_NOT_RUN"
    assert confirm_input["options"] == ["DO_NOT_RUN", "READINESS_ONLY", "RUN_S01"]

    operator_gate = data["jobs"]["operator-gate"]
    assert "environment" not in operator_gate
    gate_run = operator_gate["steps"][0]["run"]
    assert 'test "${GITHUB_REF}" = "refs/heads/main"' in gate_run
    assert "READINESS_ONLY|RUN_S01" in gate_run
    assert 'test "${{ inputs.confirm_live_gmail }}" = "RUN_S01"' not in gate_run

    steps = transport["steps"]
    step_names = [step.get("name", "") for step in steps]
    assert any("PostgreSQL" in name or "Bootstrap" in name for name in step_names)
    assert any("recipient Gmail OAuth" in name or "OAuth" in name for name in step_names)
    assert not any("live_gmail_eval" in (step.get("run") or "") for step in steps)

    recipient_step = _step_by_name(steps, "Recipient read-only")
    assert "gmail-readiness" in (recipient_step.get("run") or "")

    sender_step = _step_by_name(steps, "Sender read-only")
    sender_run = sender_step.get("run") or ""
    assert "--sender-readiness" in sender_run
    assert "--confirm-read-only" in sender_run

    readiness_step = _step_by_name(steps, "Readiness-only report")
    assert readiness_step.get("if") == "inputs.confirm_live_gmail == 'READINESS_ONLY'"
    readiness_run = readiness_step.get("run") or ""
    assert "readiness-only" in readiness_run
    assert "run-scenario" not in readiness_run

    readiness_artifact = _step_by_name(steps, "Upload readiness artifact")
    assert readiness_artifact.get("if") == "always() && inputs.confirm_live_gmail == 'READINESS_ONLY'"

    run_step = _step_by_name(steps, "Live Gmail S01 scenario")
    assert run_step.get("if") == "inputs.confirm_live_gmail == 'RUN_S01'"
    run_run = run_step.get("run") or ""
    assert "--run-id-file" in run_run
    assert "S01_lead_laddbox_quality" in run_run
    assert "--scenario-id" in run_run

    cleanup_step = next(step for step in steps if step.get("id") == "cleanup")
    assert cleanup_step.get("if") == "always() && inputs.confirm_live_gmail == 'RUN_S01'"
    assert "|| true" not in (cleanup_step.get("run") or "")

    gate_step = _step_by_name(steps, "Cleanup gate")
    assert gate_step.get("if") == "always() && inputs.confirm_live_gmail == 'RUN_S01'"
    gate_run = gate_step.get("run") or ""
    assert 'steps.cleanup.outcome }}" = "failure"' in gate_run

    artifact_step = _step_by_name(steps, "Upload redacted artifacts")
    assert artifact_step.get("if") == "always() && inputs.confirm_live_gmail == 'RUN_S01' && env.RUN_ARTIFACT_DIR != ''"
    artifact_path = str(artifact_step.get("with", {}).get("path", ""))
    assert "RUN_ARTIFACT_DIR" in artifact_path
    assert "storage/live_eval/runs" not in artifact_path
    assert artifact_step.get("with", {}).get("if-no-files-found") == "error"

    resolve_step = _step_by_name(steps, "Resolve run artifact path")
    assert resolve_step.get("if") == "always() && inputs.confirm_live_gmail == 'RUN_S01'"
    assert "resolved_run_directory" in (resolve_step.get("run") or "")

    verify_step = _step_by_name(steps, "Verify run artifacts present")
    assert verify_step.get("if") == "always() && inputs.confirm_live_gmail == 'RUN_S01' && env.RUN_ID != ''"

    transport_env = transport.get("env") or {}
    assert transport_env.get("STORAGE_PATH") == "${{ github.workspace }}/storage/ci-live-eval"

    freeform_inputs = set(dispatch["inputs"].keys()) - {"confirm_live_gmail"}
    assert not freeform_inputs, f"unexpected workflow inputs: {freeform_inputs}"


LLM_WORKFLOW_PATH = (
    Path(__file__).resolve().parents[3] / ".github" / "workflows" / "live-llm-eval.yml"
)


def _load_llm_workflow() -> dict:
    return yaml.safe_load(LLM_WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_live_llm_workflow_contract():
    data = _load_llm_workflow()
    assert data["concurrency"]["group"] == "live-llm-eval"
    trigger = _workflow_trigger(data)
    dispatch = trigger["workflow_dispatch"]
    confirm = dispatch["inputs"]["confirm_live_llm"]
    assert confirm["options"] == ["DO_NOT_RUN", "READINESS_ONLY", "RUN_LLM_S01"]

    foundation = data["jobs"]["foundation"]
    assert "environment" not in foundation
    foundation_env = foundation.get("env") or {}
    assert foundation_env.get("LIVE_LLM_EVAL_ALLOWED") in ("yes", True)
    assert "LIVE_GMAIL_EVAL_ALLOWED" not in foundation_env
    assert "secrets" not in str(foundation)

    collect_step = _step_by_name(foundation["steps"], "Verify integration_db test selection")
    assert '"30"' in (collect_step.get("run") or "")
    assert "test_llm_operations_pg.py" in (collect_step.get("run") or "")
    assert "test_live_eval_migration_021_pg.py" in (collect_step.get("run") or "")

    transport = data["jobs"]["live_llm_transport"]
    assert transport["environment"] == "live-llm-eval"
    transport_env = transport.get("env") or {}
    assert "LIVE_GMAIL" not in str(transport_env)
    assert "GMAIL" not in str(transport_env).upper() or "LIVE_EVAL_GMAIL" not in transport_env
    assert transport_env.get("LIVE_LLM_EVAL_ALLOWED") in ("yes", True)

    steps = transport["steps"]
    assert not any("OAuth" in (step.get("name") or "") for step in steps)
    assert not any("cleanup" in (step.get("name") or "").lower() for step in steps)
    readiness = _step_by_name(steps, "LLM readiness-only report")
    assert readiness.get("if") == "inputs.confirm_live_llm == 'READINESS_ONLY'"
    run_step = _step_by_name(steps, "Live LLM S01 scenario")
    assert run_step.get("if") == "inputs.confirm_live_llm == 'RUN_LLM_S01'"
    assert "run-llm-s01" in (run_step.get("run") or "")

    seed_step = _step_by_name(steps, "Seed eval tenant")
    assert seed_step is not None
    assert "--tenant-id TENANT_LIVE_EVAL" in (seed_step.get("run") or "")
    assert "--apply" in (seed_step.get("run") or "")
    assert transport_env.get("LIVE_EVAL_SEED_ALLOWED") in ("yes", True)
    assert transport_env.get("LIVE_EVAL_LLM_MODEL") == "gpt-4o-mini"
    assert transport_env.get("LLM_MODEL") == "gpt-4o-mini"
    assert transport_env.get("LLM_API_URL") == "https://api.openai.com/v1/chat/completions"
    assert "secrets.LIVE_EVAL_LLM_MODEL" not in str(transport)
    assert "secrets.LIVE_EVAL_LLM_API_URL" not in str(transport)
    secret_refs = [
        line
        for line in LLM_WORKFLOW_PATH.read_text(encoding="utf-8").splitlines()
        if "secrets." in line
    ]
    assert secret_refs == [
        '      ADMIN_API_KEY: ${{ secrets.LIVE_EVAL_ADMIN_API_KEY }}',
        '      LLM_API_KEY: ${{ secrets.LIVE_EVAL_LLM_API_KEY }}',
    ]
    assert foundation_env.get("LIVE_EVAL_LLM_MODEL") == "gpt-4o-mini"
    assert foundation_env.get("LLM_API_URL") == "https://api.openai.com/v1/chat/completions"


RELEASE_GATE_PATH = (
    Path(__file__).resolve().parents[3] / ".github" / "workflows" / "release-gate.yml"
)


def test_release_gate_llm_operations_pg_contract():
    data = yaml.safe_load(RELEASE_GATE_PATH.read_text(encoding="utf-8"))
    pg_job = data["jobs"]["live-eval-postgres"]
    steps = pg_job["steps"]
    llm_step = _step_by_name(steps, "Run live-llm operation PG contract tests")
    assert "test_llm_operations_pg.py" in (llm_step.get("run") or "")
    assert '"17"' in (llm_step.get("run") or "")
    assert "live_eval_llm_operations_pg.junit.xml --expected 17" in (llm_step.get("run") or "")
