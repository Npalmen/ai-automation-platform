"""
Tests for Slice 6 — Routing Preview + Readiness.

Covers:
- resolve_routing_preview(): ready, missing_hint, invalid_hint
- resolve_routing_readiness(): counts, percent
- GET /tenant/routing-preview/{job_type}: shape, ready/missing/invalid
- GET /tenant/routing-preview/{job_type}: invalid job_type → 400
- GET /tenant/routing-readiness: shape, counts
- Case detail GET /cases/{job_id} includes routing_preview field
- Tenant isolation (preview + readiness)
- Preserves existing case detail structure
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db():
    return MagicMock()


def _valid_hint(board_id="123", board_name="Leads", system="monday"):
    return {
        "system": system,
        "target": {
            "board_id":   board_id,
            "board_name": board_name,
            "group_id":   None,
            "group_name": None,
        },
        "confidence": "high",
        "reason": "Board name matched lead",
    }


def _memory_with_hints(hints: dict) -> dict:
    return {
        "business_profile": {},
        "system_map": {"monday": {"boards": [], "groups": [], "columns": []}, "gmail": {}},
        "routing_hints": hints,
    }


# ---------------------------------------------------------------------------
# Pure function — resolve_routing_preview
# ---------------------------------------------------------------------------

class TestResolveRoutingPreview:
    def test_ready_when_valid_hint(self):
        from app.workflows.scanners.routing_preview import resolve_routing_preview
        hints = {"lead": _valid_hint()}
        result = resolve_routing_preview(hints, "lead")
        assert result["status"] == "ready"
        assert result["job_type"] == "lead"
        assert result["system"] == "monday"
        assert result["target"]["board_id"] == "123"
        assert "Leads" in result["message"]

    def test_missing_hint_when_null(self):
        from app.workflows.scanners.routing_preview import resolve_routing_preview
        hints = {"lead": None}
        result = resolve_routing_preview(hints, "lead")
        assert result["status"] == "missing_hint"
        assert result["system"] is None
        assert result["target"] is None
        assert "lead" in result["message"]

    def test_missing_hint_when_key_absent(self):
        from app.workflows.scanners.routing_preview import resolve_routing_preview
        result = resolve_routing_preview({}, "invoice")
        assert result["status"] == "missing_hint"

    def test_invalid_hint_when_not_dict(self):
        from app.workflows.scanners.routing_preview import resolve_routing_preview
        hints = {"lead": "not-a-dict"}
        result = resolve_routing_preview(hints, "lead")
        assert result["status"] == "invalid_hint"
        assert "ofullständig" in result["message"].lower() or "invalid" in result["message"].lower()

    def test_invalid_hint_when_missing_system(self):
        from app.workflows.scanners.routing_preview import resolve_routing_preview
        bad = {"target": {"board_id": "1", "board_name": "X", "group_id": None, "group_name": None}}
        result = resolve_routing_preview({"lead": bad}, "lead")
        assert result["status"] == "invalid_hint"

    def test_invalid_hint_when_missing_target(self):
        from app.workflows.scanners.routing_preview import resolve_routing_preview
        bad = {"system": "monday"}
        result = resolve_routing_preview({"lead": bad}, "lead")
        assert result["status"] == "invalid_hint"

    def test_invalid_hint_when_empty_board_id(self):
        from app.workflows.scanners.routing_preview import resolve_routing_preview
        bad = {
            "system": "monday",
            "target": {"board_id": "", "board_name": "Leads", "group_id": None, "group_name": None},
        }
        result = resolve_routing_preview({"lead": bad}, "lead")
        assert result["status"] == "invalid_hint"

    def test_message_contains_board_name_when_ready(self):
        from app.workflows.scanners.routing_preview import resolve_routing_preview
        hints = {"invoice": _valid_hint("99", "Faktura")}
        result = resolve_routing_preview(hints, "invoice")
        assert "Faktura" in result["message"]

    def test_message_contains_job_type_when_missing(self):
        from app.workflows.scanners.routing_preview import resolve_routing_preview
        result = resolve_routing_preview({}, "customer_inquiry")
        assert "customer_inquiry" in result["message"]

    def test_returns_all_required_keys(self):
        from app.workflows.scanners.routing_preview import resolve_routing_preview
        result = resolve_routing_preview({"lead": _valid_hint()}, "lead")
        for key in ("job_type", "status", "system", "target", "message"):
            assert key in result


# ---------------------------------------------------------------------------
# Pure function — resolve_routing_readiness
# ---------------------------------------------------------------------------

class TestResolveRoutingReadiness:
    def test_all_missing_when_no_hints(self):
        from app.workflows.scanners.routing_preview import resolve_routing_readiness, SUPPORTED_JOB_TYPES
        result = resolve_routing_readiness({})
        assert result["score"]["ready_count"] == 0
        assert result["score"]["total"] == len(SUPPORTED_JOB_TYPES)
        assert result["score"]["percent"] == 0
        assert set(result["missing"]) == set(SUPPORTED_JOB_TYPES)
        assert result["ready"] == []
        assert result["invalid"] == []

    def test_one_ready(self):
        from app.workflows.scanners.routing_preview import resolve_routing_readiness
        hints = {"lead": _valid_hint()}
        result = resolve_routing_readiness(hints)
        assert "lead" in result["ready"]
        assert result["score"]["ready_count"] == 1

    def test_invalid_counted_separately(self):
        from app.workflows.scanners.routing_preview import resolve_routing_readiness
        hints = {"lead": "bad"}
        result = resolve_routing_readiness(hints)
        assert "lead" in result["invalid"]
        assert result["score"]["ready_count"] == 0

    def test_percent_calculation(self):
        from app.workflows.scanners.routing_preview import resolve_routing_readiness, SUPPORTED_JOB_TYPES
        # Make all ready
        hints = {jt: _valid_hint(str(i), f"Board {i}") for i, jt in enumerate(SUPPORTED_JOB_TYPES)}
        result = resolve_routing_readiness(hints)
        assert result["score"]["percent"] == 100
        assert result["score"]["ready_count"] == len(SUPPORTED_JOB_TYPES)

    def test_missing_does_not_include_ready(self):
        from app.workflows.scanners.routing_preview import resolve_routing_readiness
        hints = {"lead": _valid_hint(), "invoice": None}
        result = resolve_routing_readiness(hints)
        assert "lead" not in result["missing"]
        assert "invoice" in result["missing"]

    def test_score_keys_present(self):
        from app.workflows.scanners.routing_preview import resolve_routing_readiness
        result = resolve_routing_readiness({})
        assert "ready_count" in result["score"]
        assert "total" in result["score"]
        assert "percent" in result["score"]


# ---------------------------------------------------------------------------
# GET /tenant/routing-preview/{job_type} endpoint
# ---------------------------------------------------------------------------

def _call_preview(job_type, hints=None, tenant_id="T1"):
    from app.main import get_routing_preview
    db = _make_db()
    settings = {"memory": {"routing_hints": hints}} if hints is not None else {}
    with patch(
        "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
        return_value=settings,
    ):
        return get_routing_preview(job_type=job_type, db=db, tenant_id=tenant_id)


class TestGetRoutingPreviewEndpoint:
    def test_ready_response_shape(self):
        result = _call_preview("lead", hints={"lead": _valid_hint()})
        assert result["status"] == "ready"
        assert result["job_type"] == "lead"
        assert result["system"] == "monday"
        assert "target" in result
        assert "message" in result

    def test_missing_hint_status(self):
        result = _call_preview("lead", hints={"lead": None})
        assert result["status"] == "missing_hint"

    def test_invalid_hint_status(self):
        result = _call_preview("lead", hints={"lead": {"bad": "data"}})
        assert result["status"] == "invalid_hint"

    def test_invalid_job_type_raises_400(self):
        from fastapi import HTTPException
        from app.main import get_routing_preview
        db = _make_db()
        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value={},
        ):
            with pytest.raises(HTTPException) as exc:
                get_routing_preview(job_type="not_a_real_type", db=db, tenant_id="T1")
        assert exc.value.status_code == 400

    def test_tenant_isolation(self):
        def get_side(db, tid):
            if tid == "T1":
                return {"memory": {"routing_hints": {"lead": _valid_hint("1", "LeadsT1")}}}
            return {}

        from app.main import get_routing_preview
        db = _make_db()
        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            side_effect=get_side,
        ):
            r1 = get_routing_preview(job_type="lead", db=db, tenant_id="T1")
            r2 = get_routing_preview(job_type="lead", db=db, tenant_id="T2")

        assert r1["status"] == "ready"
        assert r2["status"] == "missing_hint"


# ---------------------------------------------------------------------------
# GET /tenant/routing-readiness endpoint
# ---------------------------------------------------------------------------

def _call_readiness(hints=None, tenant_id="T1"):
    from app.main import get_routing_readiness
    db = _make_db()
    settings = {"memory": {"routing_hints": hints}} if hints is not None else {}
    with patch(
        "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
        return_value=settings,
    ):
        return get_routing_readiness(db=db, tenant_id=tenant_id)


class TestGetRoutingReadinessEndpoint:
    def test_response_shape(self):
        result = _call_readiness()
        assert "ready" in result
        assert "missing" in result
        assert "invalid" in result
        assert "score" in result
        assert "ready_count" in result["score"]
        assert "total" in result["score"]
        assert "percent" in result["score"]

    def test_all_missing_when_no_hints(self):
        result = _call_readiness()
        assert result["score"]["ready_count"] == 0
        assert result["score"]["percent"] == 0

    def test_one_ready_counted(self):
        hints = {"lead": _valid_hint()}
        result = _call_readiness(hints=hints)
        assert "lead" in result["ready"]
        assert result["score"]["ready_count"] == 1

    def test_tenant_isolation(self):
        def get_side(db, tid):
            if tid == "T1":
                return {"memory": {"routing_hints": {"lead": _valid_hint()}}}
            return {}

        from app.main import get_routing_readiness
        db = _make_db()
        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            side_effect=get_side,
        ):
            r1 = get_routing_readiness(db=db, tenant_id="T1")
            r2 = get_routing_readiness(db=db, tenant_id="T2")

        assert r1["score"]["ready_count"] >= 1
        assert r2["score"]["ready_count"] == 0


# ---------------------------------------------------------------------------
# GET /cases/{job_id} includes routing_preview field
# ---------------------------------------------------------------------------

class TestCaseDetailRoutingPreview:
    def _make_job_record(self, job_type="lead"):
        r = MagicMock()
        r.job_id = "job-001"
        r.tenant_id = "T1"
        r.job_type = job_type
        r.status = "completed"
        r.input_data = {}
        r.result = {}
        r.created_at = None
        r.updated_at = None
        return r

    def _call_get_case(self, job_type="lead", hints=None):
        from app.main import get_case
        db = _make_db()
        job_record = self._make_job_record(job_type=job_type)

        # DB query returns job record
        db.query.return_value.filter.return_value.first.return_value = job_record
        # Action executions query returns empty
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        settings = {"memory": {"routing_hints": hints}} if hints is not None else {}

        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value=settings,
        ):
            return get_case(job_id="job-001", db=db, tenant_id="T1")

    def test_routing_preview_field_present(self):
        result = self._call_get_case(job_type="lead")
        assert "routing_preview" in result

    def test_routing_preview_missing_when_no_hint(self):
        result = self._call_get_case(job_type="lead", hints={"lead": None})
        rp = result["routing_preview"]
        assert rp["status"] == "missing_hint"

    def test_routing_preview_ready_when_hint_exists(self):
        result = self._call_get_case(
            job_type="lead",
            hints={"lead": _valid_hint("55", "Sales Board")},
        )
        rp = result["routing_preview"]
        assert rp["status"] == "ready"
        assert rp["target"]["board_id"] == "55"

    def test_routing_preview_none_for_unknown_job_type(self):
        result = self._call_get_case(job_type="unknown_type_xyz")
        assert result["routing_preview"] is None

    def test_existing_case_detail_fields_still_present(self):
        result = self._call_get_case()
        for field in ("job_id", "type", "status", "original_message", "actions", "errors"):
            assert field in result
