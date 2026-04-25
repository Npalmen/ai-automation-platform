"""
Tests for Slice 5 — Scanner Result Review + Routing Hint Drafts.

Covers:
- generate_routing_hint_drafts(): nulls when no system_map / boards
- Monday board detected_purpose "lead" → lead draft
- Monday board name "Leads" → lead draft (keyword fallback)
- Swedish board name "Offert" → lead draft
- "Faktura" / "Ekonomi" board → invoice draft
- "Support" / "Service" board → support draft
- Multiple candidates → deterministic first-match, confidence medium/low
- detected_purpose takes priority over name keyword match
- GET /tenant/routing-hint-drafts endpoint (shape, no system_map, with boards)
- POST /tenant/routing-hints/apply: persists selected hints
- apply does not clobber existing routing_hints for unprovided job types
- apply preserves business_profile and system_map
- unsupported job type → 422
- malformed hint → 422
- null hint allowed (clears the hint)
- tenant isolation
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_board(id="1", name="Board", detected_purpose="unknown", groups=None, columns=None):
    return {
        "id": id,
        "name": name,
        "description": "",
        "detected_purpose": detected_purpose,
        "groups":  groups or [],
        "columns": columns or [],
    }


def _memory_with_boards(boards):
    return {
        "business_profile": {"company_name": "Test AB"},
        "system_map": {
            "monday": {"boards": boards, "groups": [], "columns": []},
            "gmail":  {"known_senders": [], "subject_patterns": [], "detected_mail_types": []},
        },
        "routing_hints": {
            "lead": None, "customer_inquiry": None, "invoice": None,
            "partnership": None, "supplier": None, "support": None, "internal": None,
        },
    }


def _empty_memory():
    return {
        "business_profile": {},
        "system_map": {"monday": {"boards": [], "groups": [], "columns": []}, "gmail": {}},
        "routing_hints": {},
    }


def _make_db():
    return MagicMock()


# ---------------------------------------------------------------------------
# Pure function tests — generate_routing_hint_drafts
# ---------------------------------------------------------------------------

class TestGenerateRoutingHintDrafts:
    def test_all_null_when_no_boards(self):
        from app.workflows.scanners.routing_hint_drafts import generate_routing_hint_drafts, SUPPORTED_JOB_TYPES
        result = generate_routing_hint_drafts(_empty_memory())
        assert set(result.keys()) == set(SUPPORTED_JOB_TYPES)
        assert all(v is None for v in result.values())

    def test_all_null_when_no_system_map(self):
        from app.workflows.scanners.routing_hint_drafts import generate_routing_hint_drafts
        result = generate_routing_hint_drafts({})
        assert all(v is None for v in result.values())

    def test_lead_from_detected_purpose(self):
        from app.workflows.scanners.routing_hint_drafts import generate_routing_hint_drafts
        boards = [_make_board(id="10", name="Pipeline", detected_purpose="lead")]
        result = generate_routing_hint_drafts(_memory_with_boards(boards))
        hint = result["lead"]
        assert hint is not None
        assert hint["system"] == "monday"
        assert hint["target"]["board_id"] == "10"
        assert hint["target"]["board_name"] == "Pipeline"
        assert hint["confidence"] == "high"
        assert "lead" in hint["reason"].lower()

    def test_lead_from_board_name_leads(self):
        from app.workflows.scanners.routing_hint_drafts import generate_routing_hint_drafts
        boards = [_make_board(id="11", name="Leads", detected_purpose="unknown")]
        result = generate_routing_hint_drafts(_memory_with_boards(boards))
        hint = result["lead"]
        assert hint is not None
        assert hint["target"]["board_id"] == "11"
        assert hint["confidence"] in ("medium", "low")

    def test_lead_from_board_name_sales(self):
        from app.workflows.scanners.routing_hint_drafts import generate_routing_hint_drafts
        boards = [_make_board(id="12", name="Sales Pipeline", detected_purpose="unknown")]
        result = generate_routing_hint_drafts(_memory_with_boards(boards))
        assert result["lead"] is not None
        assert result["lead"]["target"]["board_id"] == "12"

    def test_lead_from_swedish_offert(self):
        from app.workflows.scanners.routing_hint_drafts import generate_routing_hint_drafts
        boards = [_make_board(id="13", name="Offert", detected_purpose="unknown")]
        result = generate_routing_hint_drafts(_memory_with_boards(boards))
        assert result["lead"] is not None

    def test_invoice_from_detected_purpose(self):
        from app.workflows.scanners.routing_hint_drafts import generate_routing_hint_drafts
        boards = [_make_board(id="20", name="Billing", detected_purpose="invoice")]
        result = generate_routing_hint_drafts(_memory_with_boards(boards))
        assert result["invoice"] is not None
        assert result["invoice"]["target"]["board_id"] == "20"
        assert result["invoice"]["confidence"] == "high"

    def test_invoice_from_faktura(self):
        from app.workflows.scanners.routing_hint_drafts import generate_routing_hint_drafts
        boards = [_make_board(id="21", name="Faktura", detected_purpose="unknown")]
        result = generate_routing_hint_drafts(_memory_with_boards(boards))
        assert result["invoice"] is not None

    def test_invoice_from_ekonomi(self):
        from app.workflows.scanners.routing_hint_drafts import generate_routing_hint_drafts
        boards = [_make_board(id="22", name="Ekonomi", detected_purpose="unknown")]
        result = generate_routing_hint_drafts(_memory_with_boards(boards))
        assert result["invoice"] is not None

    def test_support_from_detected_purpose(self):
        from app.workflows.scanners.routing_hint_drafts import generate_routing_hint_drafts
        boards = [_make_board(id="30", name="Misc Board", detected_purpose="support")]
        result = generate_routing_hint_drafts(_memory_with_boards(boards))
        assert result["support"] is not None
        assert result["support"]["confidence"] == "high"

    def test_support_from_board_name_support(self):
        from app.workflows.scanners.routing_hint_drafts import generate_routing_hint_drafts
        boards = [_make_board(id="31", name="Support", detected_purpose="unknown")]
        result = generate_routing_hint_drafts(_memory_with_boards(boards))
        assert result["support"] is not None

    def test_support_from_board_name_service(self):
        from app.workflows.scanners.routing_hint_drafts import generate_routing_hint_drafts
        boards = [_make_board(id="32", name="Service Desk", detected_purpose="unknown")]
        result = generate_routing_hint_drafts(_memory_with_boards(boards))
        assert result["support"] is not None

    def test_no_match_returns_null(self):
        from app.workflows.scanners.routing_hint_drafts import generate_routing_hint_drafts
        boards = [_make_board(id="99", name="Random Board XYZ", detected_purpose="unknown")]
        result = generate_routing_hint_drafts(_memory_with_boards(boards))
        assert result["lead"] is None
        assert result["invoice"] is None
        assert result["support"] is None

    def test_multiple_purpose_candidates_medium_confidence(self):
        from app.workflows.scanners.routing_hint_drafts import generate_routing_hint_drafts
        boards = [
            _make_board(id="40", name="Leads A", detected_purpose="lead"),
            _make_board(id="41", name="Leads B", detected_purpose="lead"),
        ]
        result = generate_routing_hint_drafts(_memory_with_boards(boards))
        assert result["lead"] is not None
        assert result["lead"]["target"]["board_id"] == "40"
        assert result["lead"]["confidence"] == "medium"

    def test_multiple_name_candidates_low_confidence(self):
        from app.workflows.scanners.routing_hint_drafts import generate_routing_hint_drafts
        boards = [
            _make_board(id="50", name="Faktura A", detected_purpose="unknown"),
            _make_board(id="51", name="Faktura B", detected_purpose="unknown"),
        ]
        result = generate_routing_hint_drafts(_memory_with_boards(boards))
        assert result["invoice"] is not None
        assert result["invoice"]["target"]["board_id"] == "50"
        assert result["invoice"]["confidence"] == "low"

    def test_detected_purpose_takes_priority_over_name(self):
        from app.workflows.scanners.routing_hint_drafts import generate_routing_hint_drafts
        # Board "99" has name "Leads" but purpose is support;
        # Board "100" has detected_purpose lead.
        boards = [
            _make_board(id="99", name="Leads but actually support", detected_purpose="support"),
            _make_board(id="100", name="CRM", detected_purpose="lead"),
        ]
        result = generate_routing_hint_drafts(_memory_with_boards(boards))
        assert result["lead"]["target"]["board_id"] == "100"

    def test_returns_all_supported_job_types(self):
        from app.workflows.scanners.routing_hint_drafts import generate_routing_hint_drafts, SUPPORTED_JOB_TYPES
        result = generate_routing_hint_drafts(_empty_memory())
        for jt in SUPPORTED_JOB_TYPES:
            assert jt in result

    def test_target_shape_has_required_keys(self):
        from app.workflows.scanners.routing_hint_drafts import generate_routing_hint_drafts
        boards = [_make_board(id="55", name="Leads", detected_purpose="lead")]
        result = generate_routing_hint_drafts(_memory_with_boards(boards))
        target = result["lead"]["target"]
        assert "board_id" in target
        assert "board_name" in target
        assert "group_id" in target
        assert "group_name" in target


# ---------------------------------------------------------------------------
# GET /tenant/routing-hint-drafts endpoint
# ---------------------------------------------------------------------------

def _call_get_drafts(memory_settings=None, tenant_id="T1"):
    from app.main import get_routing_hint_drafts
    db = _make_db()
    settings_data = memory_settings if memory_settings is not None else {}

    with patch(
        "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
        return_value=settings_data,
    ):
        return get_routing_hint_drafts(db=db, tenant_id=tenant_id)


class TestGetRoutingHintDraftsEndpoint:
    def test_returns_dict_for_all_supported_types(self):
        from app.workflows.scanners.routing_hint_drafts import SUPPORTED_JOB_TYPES
        result = _call_get_drafts()
        for jt in SUPPORTED_JOB_TYPES:
            assert jt in result

    def test_all_null_when_no_boards(self):
        result = _call_get_drafts()
        assert all(v is None for v in result.values())

    def test_returns_lead_hint_when_lead_board_present(self):
        settings = {
            "memory": {
                "system_map": {
                    "monday": {
                        "boards": [_make_board(id="77", name="Leads", detected_purpose="lead")],
                        "groups": [],
                        "columns": [],
                    }
                }
            }
        }
        result = _call_get_drafts(memory_settings=settings)
        assert result["lead"] is not None
        assert result["lead"]["target"]["board_id"] == "77"

    def test_tenant_isolation(self):
        settings_t1 = {
            "memory": {
                "system_map": {
                    "monday": {
                        "boards": [_make_board(id="1", name="Leads", detected_purpose="lead")],
                        "groups": [], "columns": [],
                    }
                }
            }
        }
        settings_t2 = {}

        def get_settings_side_effect(db, tenant_id):
            return settings_t1 if tenant_id == "T1" else settings_t2

        from app.main import get_routing_hint_drafts
        db = _make_db()

        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            side_effect=get_settings_side_effect,
        ):
            r1 = get_routing_hint_drafts(db=db, tenant_id="T1")
            r2 = get_routing_hint_drafts(db=db, tenant_id="T2")

        assert r1["lead"] is not None
        assert r2["lead"] is None


# ---------------------------------------------------------------------------
# POST /tenant/routing-hints/apply endpoint
# ---------------------------------------------------------------------------

def _call_apply(routing_hints: dict, existing: dict | None = None, tenant_id: str = "T1"):
    from app.main import apply_routing_hints, RoutingHintApplyRequest
    db = _make_db()
    captured = {}

    def fake_update(db, tid, settings):
        captured.update(settings)

    with (
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value=existing or {},
        ),
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings",
            side_effect=fake_update,
        ),
    ):
        req = RoutingHintApplyRequest(routing_hints=routing_hints)
        result = apply_routing_hints(request=req, db=db, tenant_id=tenant_id)

    return result, captured


def _valid_hint(board_id="123", board_name="Leads"):
    return {
        "system": "monday",
        "target": {
            "board_id": board_id,
            "board_name": board_name,
            "group_id": None,
            "group_name": None,
        },
        "confidence": "high",
        "reason": "Board name matched lead",
    }


class TestApplyRoutingHintsEndpoint:
    def test_persists_hint_for_job_type(self):
        result, saved = _call_apply({"lead": _valid_hint("123", "Leads")})
        assert result["status"] == "ok"
        assert saved["memory"]["routing_hints"]["lead"]["target"]["board_id"] == "123"

    def test_does_not_clobber_existing_hints_for_other_types(self):
        existing = {
            "memory": {
                "routing_hints": {
                    "invoice": {"system": "monday", "target": {"board_id": "999"}, "confidence": "high", "reason": "x"}
                }
            }
        }
        _, saved = _call_apply({"lead": _valid_hint()}, existing=existing)
        assert saved["memory"]["routing_hints"]["invoice"]["target"]["board_id"] == "999"

    def test_preserves_business_profile(self):
        existing = {"memory": {"business_profile": {"company_name": "Safe AB"}}}
        _, saved = _call_apply({"lead": _valid_hint()}, existing=existing)
        assert saved["memory"]["business_profile"]["company_name"] == "Safe AB"

    def test_preserves_system_map(self):
        existing = {
            "memory": {
                "system_map": {
                    "monday": {"boards": [{"id": "kept"}], "groups": [], "columns": []}
                }
            }
        }
        _, saved = _call_apply({"lead": _valid_hint()}, existing=existing)
        assert saved["memory"]["system_map"]["monday"]["boards"][0]["id"] == "kept"

    def test_null_hint_clears_existing(self):
        existing = {
            "memory": {"routing_hints": {"lead": _valid_hint()}}
        }
        _, saved = _call_apply({"lead": None}, existing=existing)
        assert saved["memory"]["routing_hints"]["lead"] is None

    def test_returns_routing_hints_in_response(self):
        result, _ = _call_apply({"lead": _valid_hint("77", "Sales")})
        assert "routing_hints" in result
        assert result["routing_hints"]["lead"]["target"]["board_id"] == "77"

    def test_unsupported_job_type_raises_422(self):
        from fastapi import HTTPException
        from app.main import apply_routing_hints, RoutingHintApplyRequest
        db = _make_db()
        with (
            patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings", return_value={}),
            patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings"),
        ):
            req = RoutingHintApplyRequest(routing_hints={"unknown_type_xyz": _valid_hint()})
            with pytest.raises(HTTPException) as exc:
                apply_routing_hints(request=req, db=db, tenant_id="T1")
        assert exc.value.status_code == 422
        assert "unknown_type_xyz" in str(exc.value.detail)

    def test_malformed_hint_not_dict_raises_422(self):
        from fastapi import HTTPException
        from app.main import apply_routing_hints, RoutingHintApplyRequest
        db = _make_db()
        with (
            patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings", return_value={}),
            patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings"),
        ):
            req = RoutingHintApplyRequest(routing_hints={"lead": "not-a-dict"})
            with pytest.raises(HTTPException) as exc:
                apply_routing_hints(request=req, db=db, tenant_id="T1")
        assert exc.value.status_code == 422

    def test_malformed_hint_missing_system_raises_422(self):
        from fastapi import HTTPException
        from app.main import apply_routing_hints, RoutingHintApplyRequest
        db = _make_db()
        bad_hint = {"target": {"board_id": "1", "board_name": "X", "group_id": None, "group_name": None}}
        with (
            patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings", return_value={}),
            patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings"),
        ):
            req = RoutingHintApplyRequest(routing_hints={"lead": bad_hint})
            with pytest.raises(HTTPException) as exc:
                apply_routing_hints(request=req, db=db, tenant_id="T1")
        assert exc.value.status_code == 422

    def test_invalid_confidence_raises_422(self):
        from fastapi import HTTPException
        from app.main import apply_routing_hints, RoutingHintApplyRequest
        db = _make_db()
        bad_hint = {
            "system": "monday",
            "target": {"board_id": "1", "board_name": "X", "group_id": None, "group_name": None},
            "confidence": "super-high",
            "reason": "x",
        }
        with (
            patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings", return_value={}),
            patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings"),
        ):
            req = RoutingHintApplyRequest(routing_hints={"lead": bad_hint})
            with pytest.raises(HTTPException) as exc:
                apply_routing_hints(request=req, db=db, tenant_id="T1")
        assert exc.value.status_code == 422

    def test_unknown_hint_key_raises_422(self):
        from fastapi import HTTPException
        from app.main import apply_routing_hints, RoutingHintApplyRequest
        db = _make_db()
        bad_hint = {
            "system": "monday",
            "target": {"board_id": "1", "board_name": "X", "group_id": None, "group_name": None},
            "confidence": "high",
            "reason": "x",
            "extra_unknown_key": "bad",
        }
        with (
            patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings", return_value={}),
            patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings"),
        ):
            req = RoutingHintApplyRequest(routing_hints={"lead": bad_hint})
            with pytest.raises(HTTPException) as exc:
                apply_routing_hints(request=req, db=db, tenant_id="T1")
        assert exc.value.status_code == 422

    def test_tenant_isolation(self):
        settings_store = {"T1": {}, "T2": {}}

        def fake_get(db, tid):
            return settings_store[tid]

        def fake_update(db, tid, settings):
            settings_store[tid] = settings

        from app.main import apply_routing_hints, RoutingHintApplyRequest
        db = _make_db()

        with (
            patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings", side_effect=fake_get),
            patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings", side_effect=fake_update),
        ):
            req1 = RoutingHintApplyRequest(routing_hints={"lead": _valid_hint("111", "Leads T1")})
            apply_routing_hints(request=req1, db=db, tenant_id="T1")

        assert settings_store["T2"].get("memory") is None or \
               settings_store["T2"].get("memory", {}).get("routing_hints", {}).get("lead") is None
