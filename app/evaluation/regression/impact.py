"""Deterministic path-based regression impact selection."""

from __future__ import annotations

from pathlib import Path

from app.evaluation.regression.registry import suite_entries

IMPACT_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("app/decisioning/",), ("release-gate-hermetic", "full-function-contract", "pg-eval-suite")),
    (("app/workflows/",), ("release-gate-hermetic", "full-function-contract", "pg-eval-suite")),
    (("app/integrations/google/",), ("release-gate-hermetic", "full-function-contract", "workflow-live-eval-contract")),
    (("app/domain/customer/",), ("customer-domain-manifest-contract", "pg-eval-suite", "full-function-contract")),
    (("app/api/routes/end_customer",), ("customer-domain-manifest-contract", "pg-eval-suite")),
    (("migrations/",), ("migration-chain-bootstrap", "pg-eval-suite")),
    ((".github/workflows/",), ("workflow-live-eval-contract",)),
    (("app/evaluation/",), ("regression-registry-contract", "tbr-scenarios", "full-function-contract", "customer-domain-manifest-contract")),
    (("app/core/settings.py", "app/core/settings/",), ("release-gate-hermetic", "full-function-contract")),
)

CONSERVATIVE_FALLBACK = (
    "regression-registry-contract",
    "tbr-scenarios",
    "full-function-contract",
    "customer-domain-manifest-contract",
    "workflow-live-eval-contract",
    "release-gate-hermetic",
)

ALWAYS_RUN_SUITE_IDS = {
    entry["id"]
    for entry in suite_entries()
    if entry.get("always_run_paths")
}


def normalize_changed_paths(paths: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw in paths:
        path = raw.replace("\\", "/").lstrip("./")
        if path:
            normalized.append(path)
    return normalized


def select_suites_for_changes(
    changed_paths: list[str],
    *,
    tier: str,
    available_suite_ids: set[str] | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Return selected suite IDs and skip reasons for paths outside tier."""
    available = available_suite_ids or {entry["id"] for entry in suite_entries() if tier in entry.get("tier", [])}
    if not changed_paths:
        selected = sorted(available)
        return selected, {}

    selected: set[str] = set(ALWAYS_RUN_SUITE_IDS & available)
    skip_reasons: dict[str, str] = {}
    matched = False
    for path in normalize_changed_paths(changed_paths):
        path_matched = False
        for prefixes, suite_ids in IMPACT_RULES:
            if any(path.startswith(prefix) for prefix in prefixes):
                path_matched = True
                matched = True
                selected.update(suite_id for suite_id in suite_ids if suite_id in available)
        if not path_matched:
            selected.update(suite_id for suite_id in CONSERVATIVE_FALLBACK if suite_id in available)
            matched = True
    if not matched:
        selected.update(suite_id for suite_id in CONSERVATIVE_FALLBACK if suite_id in available)

    for suite_id in sorted(available):
        if suite_id not in selected:
            skip_reasons[suite_id] = "not_impacted_by_changed_paths"
    return sorted(selected), skip_reasons


def is_shared_core_change(changed_paths: list[str]) -> bool:
    core_prefixes = (
        "app/workflows/",
        "app/decisioning/",
        "app/evaluation/",
        "migrations/",
    )
    return any(
        any(path.startswith(prefix) for prefix in core_prefixes)
        for path in normalize_changed_paths(changed_paths)
    )
