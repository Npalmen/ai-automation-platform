"""Security contract integrity tests (Kapitel 11)."""

from __future__ import annotations

import re

import pytest
from fastapi.routing import APIRoute

from app.admin.security.critical_actions import CRITICAL_ACTIONS, contracts_by_path_method
from app.main import app


def _normalize_path(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path)


def _route_index() -> dict[tuple[str, str], APIRoute]:
    out: dict[tuple[str, str], APIRoute] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        norm = _normalize_path(route.path)
        for method in route.methods or []:
            if method in {"HEAD", "OPTIONS"}:
                continue
            out[(norm, method.upper())] = route
    return out


@pytest.mark.parametrize("contract", CRITICAL_ACTIONS, ids=lambda c: c.action_key)
def test_critical_action_route_registered(contract):
    routes = _route_index()
    norm_path = _normalize_path(contract.path)
    key = (norm_path, contract.method.upper())
    assert key in routes, f"Missing route for {contract.action_key}: {contract.method} {contract.path}"


def test_no_get_run_all_mutation_route():
    routes = _route_index()
    assert ("/admin/alerts/run-all", "GET") not in routes
    assert ("/admin/alerts/run-all", "POST") in routes


def test_registry_has_recovery_and_support_contracts():
    keys = {c.action_key for c in CRITICAL_ACTIONS}
    assert "recovery.retry" in keys
    assert "support.force-inbox-sync" in keys
    assert "tenant.rotate_key" in keys
    assert "alerts.run_all" in keys


def test_contracts_unique_path_method():
    seen: set[tuple[str, str]] = set()
    for contract in CRITICAL_ACTIONS:
        key = (contract.path, contract.method.upper())
        assert key not in seen, f"Duplicate contract: {key}"
        seen.add(key)


def test_contracts_by_path_method_matches_registry():
    assert len(contracts_by_path_method()) == len(CRITICAL_ACTIONS)
