"""Canonical external routing resolver tests."""

from __future__ import annotations

from app.workflows.scanners.external_routing_resolver import (
    CANONICAL_SOURCE,
    LEGACY_SOURCE,
    resolve_effective_dispatch_hint,
    resolve_effective_routing_preview,
)


def _canonical_settings(board_id: str = "77", board_name: str = "Canonical Board"):
    return {
        "integrations": {
            "external_routing_targets": {
                "lead": {
                    "target_type": "monday_board",
                    "board_id": board_id,
                    "board_name": board_name,
                }
            }
        }
    }


def _legacy_memory(board_id: str = "99", board_name: str = "Legacy Board"):
    return {
        "routing_hints": {
            "lead": {
                "system": "monday",
                "target": {
                    "board_id": board_id,
                    "board_name": board_name,
                    "group_id": None,
                    "group_name": None,
                },
            }
        }
    }


class TestExternalRoutingResolver:
    def test_canonical_takes_precedence_over_legacy(self):
        hint, source = resolve_effective_dispatch_hint(
            job_type="lead",
            tenant_settings=_canonical_settings(),
            memory=_legacy_memory(),
        )
        assert source == CANONICAL_SOURCE
        assert hint["target"]["board_id"] == "77"

    def test_legacy_fallback_when_canonical_missing(self):
        hint, source = resolve_effective_dispatch_hint(
            job_type="lead",
            tenant_settings={},
            memory=_legacy_memory(),
        )
        assert source == LEGACY_SOURCE
        assert hint["target"]["board_id"] == "99"

    def test_invalid_canonical_does_not_fallback_to_legacy(self):
        hint, source = resolve_effective_dispatch_hint(
            job_type="lead",
            tenant_settings={
                "integrations": {
                    "external_routing_targets": {
                        "lead": {"target_type": "unknown_type", "board_id": "1"}
                    }
                }
            },
            memory=_legacy_memory(),
        )
        assert source == CANONICAL_SOURCE
        assert hint["system"] == "manual_review"

    def test_preview_marks_invalid_canonical_manual_review(self):
        preview = resolve_effective_routing_preview(
            job_type="lead",
            tenant_settings={
                "integrations": {
                    "external_routing_targets": {
                        "lead": {"target_type": "hubspot", "board_id": "1", "board_name": "X"}
                    }
                }
            },
            memory=_legacy_memory(),
        )
        assert preview["routing_source"] == CANONICAL_SOURCE
        assert preview["status"] == "invalid_hint"

    def test_string_internal_routes_ignored_in_legacy(self):
        hint, source = resolve_effective_dispatch_hint(
            job_type="lead",
            tenant_settings={},
            memory={"routing_hints": {"lead": "internal_queue"}},
        )
        assert hint is None
        assert source == "missing"
