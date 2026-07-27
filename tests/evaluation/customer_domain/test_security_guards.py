"""Security guard tests for customer-domain stateful evaluation."""

from __future__ import annotations

import pytest

from app.evaluation.customer_domain.controls import run_security_controls
from app.evaluation.customer_domain.db import cleanup_eval_tenants, initialize_database
from app.evaluation.customer_domain.guards import ExternalSideEffectGuard, install_external_guards
from app.evaluation.customer_domain.reporting import _scan_for_credentials
from tests.helpers.customer_domain_eval_pg import eval_engine


def test_credential_scan_detects_forbidden_keys():
    assert _scan_for_credentials({"api_key": "secret"}) is True
    assert _scan_for_credentials({"status": "ok"}) is False


def test_install_external_guards_returns_patch_targets():
    guard = ExternalSideEffectGuard()
    patches = install_external_guards(guard)
    assert isinstance(patches, list)


@pytest.mark.pg_eval
def test_security_controls_pass_on_eval_tenant():
    engine = eval_engine()
    initialize_database(engine)
    cleanup_eval_tenants(engine)
    try:
        result = run_security_controls(engine, "eval_cd_security_pg")
        assert result["result"] == "PASS"
    finally:
        cleanup_eval_tenants(engine)
        engine.dispose()
