"""Hermetic tests for live LLM readiness (0 provider calls)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.settings import get_settings
from app.evaluation.live.config import get_live_eval_config
from app.evaluation.live.llm_readiness import (
    LIVE_LLM_PINNED_API_URL,
    LIVE_LLM_PINNED_CALL_BUDGET,
    LIVE_LLM_PINNED_MODEL,
    LIVE_LLM_PINNED_PROVIDER,
    LIVE_LLM_READINESS_SCHEMA_VERSION,
    build_llm_readiness_artifact,
    run_llm_offline_readiness_checks,
    run_llm_readiness_checks,
)
from app.repositories.postgres.database import Base
from app.repositories.postgres.live_eval_models import LiveEvalRunRow
from app.repositories.postgres.tenant_config_models import TenantConfigRecord


def _clear_caches():
    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


@pytest.fixture
def live_llm_readiness_env(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_LLM_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", "TENANT_LIVE_EVAL")
    monkeypatch.setenv("LIVE_EVAL_LLM_PROVIDER", LIVE_LLM_PINNED_PROVIDER)
    monkeypatch.setenv("LIVE_EVAL_LLM_MODEL", LIVE_LLM_PINNED_MODEL)
    monkeypatch.setenv("LIVE_EVAL_LLM_TIMEOUT", "60")
    monkeypatch.setenv("LIVE_EVAL_LLM_MAX_TOKENS", "2048")
    monkeypatch.setenv("LIVE_EVAL_MAX_LLM_CALLS", str(LIVE_LLM_PINNED_CALL_BUDGET))
    monkeypatch.setenv("LLM_API_URL", LIVE_LLM_PINNED_API_URL)
    monkeypatch.setenv("LLM_MODEL", LIVE_LLM_PINNED_MODEL)
    monkeypatch.setenv("LLM_RETRY_ATTEMPTS", "0")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.0")
    monkeypatch.setenv("LLM_API_KEY", "eval-llm-secret-key")
    monkeypatch.setenv("ADMIN_API_KEY", "eval-admin-secret-key")
    monkeypatch.setenv("LIVE_EVAL_SEED_ALLOWED", "yes")
    monkeypatch.setenv("BUILD_GIT_SHA", "a045b80c42240b45b6de734a11d64813a40ca58d")
    _clear_caches()
    yield
    _clear_caches()


@pytest.fixture
def readiness_db(live_llm_readiness_env):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[TenantConfigRecord.__table__, LiveEvalRunRow.__table__],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _passing_report(readiness_db):
    return run_llm_readiness_checks(readiness_db, "TENANT_LIVE_EVAL")


def test_readiness_makes_no_provider_calls(live_llm_readiness_env, readiness_db):
    with patch("app.ai.llm.client.LLMClient.generate_json_detailed") as mocked:
        report = _passing_report(readiness_db)
        mocked.assert_not_called()
    assert report.ready is True
    assert report.checks["live_llm_calls"] == 0
    assert report.checks["llm_operations"] == 0
    assert report.checks["model_identity_contract_ok"] is True
    assert report.checks["model_identity_registry_fingerprint"]


def test_missing_llm_api_key_fails_without_provider_calls(live_llm_readiness_env, readiness_db, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    _clear_caches()
    report = run_llm_readiness_checks(readiness_db, "TENANT_LIVE_EVAL")
    assert report.ready is False
    assert any("LLM_API_KEY" in issue for issue in report.issues)
    assert report.checks["llm_api_key_configured"] is False
    assert report.checks["live_llm_calls"] == 0


def test_missing_admin_api_key_fails_without_provider_calls(live_llm_readiness_env, readiness_db, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "")
    _clear_caches()
    report = run_llm_readiness_checks(readiness_db, "TENANT_LIVE_EVAL")
    assert report.ready is False
    assert any("ADMIN_API_KEY" in issue for issue in report.issues)
    assert report.checks["admin_api_key_configured"] is False


@pytest.mark.parametrize(
    "env_name,env_value",
    [
        ("LLM_API_KEY", "   "),
        ("ADMIN_API_KEY", ""),
    ],
)
def test_whitespace_secret_fails(live_llm_readiness_env, readiness_db, monkeypatch, env_name, env_value):
    monkeypatch.setenv(env_name, env_value)
    _clear_caches()
    report = run_llm_readiness_checks(readiness_db, "TENANT_LIVE_EVAL")
    assert report.ready is False


def test_ci_placeholder_admin_key_fails(live_llm_readiness_env, readiness_db, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "ci-admin-key")
    _clear_caches()
    report = run_llm_readiness_checks(readiness_db, "TENANT_LIVE_EVAL")
    assert report.ready is False
    assert report.checks["admin_api_key_configured"] is False


def test_correct_secret_binding_passes(live_llm_readiness_env, readiness_db):
    report = _passing_report(readiness_db)
    assert report.ready is True
    assert report.checks["llm_api_key_configured"] is True
    assert report.checks["admin_api_key_configured"] is True


@pytest.mark.parametrize(
    "env_name,env_value,issue_fragment",
    [
        ("LIVE_EVAL_LLM_PROVIDER", "anthropic", "LIVE_EVAL_LLM_PROVIDER"),
        ("LIVE_EVAL_LLM_MODEL", "gpt-4.1", "LIVE_EVAL_LLM_MODEL"),
        ("LLM_API_URL", "https://example.com/v1/chat/completions", "LLM_API_URL"),
        ("LIVE_EVAL_MAX_LLM_CALLS", "3", "LIVE_EVAL_MAX_LLM_CALLS"),
        ("LIVE_EVAL_LLM_TIMEOUT", "30", "LIVE_EVAL_LLM_TIMEOUT"),
        ("LIVE_EVAL_LLM_MAX_TOKENS", "1024", "LIVE_EVAL_LLM_MAX_TOKENS"),
        ("LLM_RETRY_ATTEMPTS", "2", "LLM_RETRY_ATTEMPTS"),
        ("LLM_TEMPERATURE", "0.1", "LLM_TEMPERATURE"),
    ],
)
def test_pinned_contract_mismatch_fails(
    live_llm_readiness_env,
    readiness_db,
    monkeypatch,
    env_name,
    env_value,
    issue_fragment,
):
    monkeypatch.setenv(env_name, env_value)
    _clear_caches()
    report = run_llm_readiness_checks(readiness_db, "TENANT_LIVE_EVAL")
    assert report.ready is False
    assert any(issue_fragment in issue for issue in report.issues)


def test_seed_gate_required_for_transport_readiness(live_llm_readiness_env, readiness_db, monkeypatch):
    monkeypatch.delenv("LIVE_EVAL_SEED_ALLOWED", raising=False)
    _clear_caches()
    report = run_llm_readiness_checks(readiness_db, "TENANT_LIVE_EVAL")
    assert report.ready is False
    assert any("LIVE_EVAL_SEED_ALLOWED" in issue for issue in report.issues)
    assert report.checks["seed_gate"] is False


def test_readiness_does_not_register_eval_run(live_llm_readiness_env, readiness_db):
    before = readiness_db.query(LiveEvalRunRow).count()
    report = _passing_report(readiness_db)
    after = readiness_db.query(LiveEvalRunRow).count()
    assert report.ready is True
    assert before == after == 0


def test_readiness_artifact_is_redacted(live_llm_readiness_env, readiness_db, tmp_path):
    report = _passing_report(readiness_db)
    artifact = build_llm_readiness_artifact(report)
    serialized = json.dumps(artifact)
    assert artifact["report_schema_version"] == LIVE_LLM_READINESS_SCHEMA_VERSION
    assert artifact["llm_provider"] == LIVE_LLM_PINNED_PROVIDER
    assert artifact["llm_requested_model"] == LIVE_LLM_PINNED_MODEL
    assert artifact["api_endpoint"] == LIVE_LLM_PINNED_API_URL
    assert artifact["gmail_required"] is False
    assert artifact["seed_gate"] is True
    assert artifact["live_llm_calls"] == 0
    assert artifact["llm_operations"] == 0
    assert artifact["external_writes"] == 0
    assert "eval-llm-secret-key" not in serialized
    assert "eval-admin-secret-key" not in serialized
    assert "Bearer" not in serialized
    assert "Authorization" not in serialized

    report_file = tmp_path / "llm_readiness_report.json"
    report_file.write_text(serialized + "\n", encoding="utf-8")
    loaded = json.loads(report_file.read_text(encoding="utf-8"))
    assert loaded["ready"] is True


def test_offline_readiness_does_not_require_secret_binding(live_llm_readiness_env, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("ADMIN_API_KEY", "")
    _clear_caches()
    report = run_llm_offline_readiness_checks()
    assert report.checks["llm_api_key_configured"] is False
    assert report.checks["admin_api_key_configured"] is False
    assert report.checks["seed_gate"] is None
    assert report.ready is True
