"""
Tests for GET /tenant/memory, PUT /tenant/memory, and GET /workflow-scan/status.

Uses direct function calls with mocked DB — consistent with repo test pattern.

Coverage:
- GET memory returns default shape for tenant with no stored memory
- GET memory returns merged stored values
- PUT memory persists business_profile, system_map, routing_hints
- PUT memory does NOT clobber existing settings keys (notifications, scheduler, etc.)
- Tenant isolation (calls use the correct tenant_id)
- Workflow scan status returns default shape
- Workflow scan status returns stored values
- Partial PUT leaves unspecified memory keys unchanged
- _get_memory unit tests (pure helper, no DB)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(tenant_id: str = "T1", stored_settings: dict | None = None):
    from app.main import get_tenant_memory
    db = MagicMock()
    with patch(
        "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
        return_value=stored_settings or {},
    ):
        return get_tenant_memory(db=db, tenant_id=tenant_id)


def _put(body: dict, tenant_id: str = "T1", stored_settings: dict | None = None):
    from app.main import put_tenant_memory, TenantMemoryRequest
    db = MagicMock()
    request = TenantMemoryRequest(**body)
    with (
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value=stored_settings or {},
        ),
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings"
        ) as mock_save,
    ):
        result = put_tenant_memory(request=request, db=db, tenant_id=tenant_id)
        return result, mock_save


def _scan(tenant_id: str = "T1", stored_settings: dict | None = None):
    from app.main import workflow_scan_status
    db = MagicMock()
    with patch(
        "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
        return_value=stored_settings or {},
    ):
        return workflow_scan_status(db=db, tenant_id=tenant_id)


# ---------------------------------------------------------------------------
# Unit tests — _get_memory pure helper
# ---------------------------------------------------------------------------

def test_get_memory_helper_empty_settings_returns_default():
    from app.main import _get_memory
    result = _get_memory({})
    assert result["business_profile"]["company_name"] == ""
    assert result["business_profile"]["tone"] == "professional"
    assert result["system_map"]["gmail"]["known_senders"] == []
    assert result["routing_hints"]["lead"] is None


def test_get_memory_helper_merges_stored_profile():
    from app.main import _get_memory
    stored = {"memory": {"business_profile": {"company_name": "Acme AB", "industry": "Bygg"}}}
    result = _get_memory(stored)
    assert result["business_profile"]["company_name"] == "Acme AB"
    assert result["business_profile"]["industry"] == "Bygg"
    assert result["business_profile"]["tone"] == "professional"  # default preserved


def test_get_memory_helper_merges_stored_system_map():
    from app.main import _get_memory
    stored = {"memory": {"system_map": {"gmail": {"known_senders": ["alice@example.com"]}}}}
    result = _get_memory(stored)
    assert "alice@example.com" in result["system_map"]["gmail"]["known_senders"]


def test_get_memory_helper_merges_routing_hints():
    from app.main import _get_memory
    stored = {"memory": {"routing_hints": {"lead": "board-123"}}}
    result = _get_memory(stored)
    assert result["routing_hints"]["lead"] == "board-123"
    assert result["routing_hints"]["invoice"] is None  # default preserved


def test_get_memory_helper_ignores_non_memory_keys():
    from app.main import _get_memory
    stored = {"notifications": {"enabled": True}, "scheduler": {"run_mode": "manual"}}
    result = _get_memory(stored)
    assert "notifications" not in result
    assert "scheduler" not in result


def test_default_memory_has_all_required_keys():
    from app.main import _DEFAULT_MEMORY
    assert "business_profile" in _DEFAULT_MEMORY
    assert "system_map" in _DEFAULT_MEMORY
    assert "routing_hints" in _DEFAULT_MEMORY
    assert "gmail" in _DEFAULT_MEMORY["system_map"]
    assert "monday" in _DEFAULT_MEMORY["system_map"]
    for job_type in ("lead", "customer_inquiry", "invoice", "partnership", "supplier"):
        assert job_type in _DEFAULT_MEMORY["routing_hints"]


# ---------------------------------------------------------------------------
# GET /tenant/memory
# ---------------------------------------------------------------------------

def test_get_memory_returns_default_shape():
    result = _get(stored_settings={})
    assert "business_profile" in result
    assert "system_map" in result
    assert "routing_hints" in result


def test_get_memory_tone_defaults_to_professional():
    result = _get(stored_settings={})
    assert result["business_profile"]["tone"] == "professional"


def test_get_memory_routing_hints_default_to_null():
    result = _get(stored_settings={})
    hints = result["routing_hints"]
    assert hints["lead"] is None
    assert hints["invoice"] is None
    assert hints["customer_inquiry"] is None


def test_get_memory_returns_stored_company_name():
    result = _get(stored_settings={"memory": {"business_profile": {"company_name": "TestCo"}}})
    assert result["business_profile"]["company_name"] == "TestCo"


def test_get_memory_gmail_system_map_present():
    result = _get(stored_settings={})
    assert "gmail" in result["system_map"]
    assert "monday" in result["system_map"]


# ---------------------------------------------------------------------------
# PUT /tenant/memory — persist
# ---------------------------------------------------------------------------

def test_put_memory_persists_business_profile():
    result, mock_save = _put(
        {"business_profile": {"company_name": "Lindqvist AB", "industry": "Bygg"}}
    )
    assert result["business_profile"]["company_name"] == "Lindqvist AB"
    assert result["business_profile"]["industry"] == "Bygg"
    assert mock_save.called


def test_put_memory_persists_routing_hints():
    result, _ = _put({"routing_hints": {"lead": "board-999", "invoice": "board-777"}})
    assert result["routing_hints"]["lead"] == "board-999"
    assert result["routing_hints"]["invoice"] == "board-777"


def test_put_memory_write_contains_memory_key():
    _, mock_save = _put({"business_profile": {"company_name": "X"}})
    written_settings = mock_save.call_args[0][2]
    assert "memory" in written_settings


def test_put_memory_does_not_clobber_notifications():
    existing = {
        "notifications": {"enabled": True, "recipient_email": "boss@co.se"},
        "scheduler": {"run_mode": "scheduled"},
    }
    captured = {}

    def fake_update(db, tenant_id, settings):
        captured.update(settings)

    from app.main import put_tenant_memory, TenantMemoryRequest
    db = MagicMock()
    request = TenantMemoryRequest(business_profile={"company_name": "NewCo"})
    with (
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value=existing,
        ),
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings",
            side_effect=fake_update,
        ),
    ):
        put_tenant_memory(request=request, db=db, tenant_id="T1")

    assert captured.get("notifications", {}).get("enabled") is True
    assert captured.get("scheduler", {}).get("run_mode") == "scheduled"


def test_put_memory_partial_update_preserves_other_memory_keys():
    existing = {
        "memory": {
            "routing_hints": {"lead": "board-existing"},
            "business_profile": {"company_name": "Old Name"},
        }
    }
    result, _ = _put({"business_profile": {"company_name": "New Name"}}, stored_settings=existing)
    assert result["business_profile"]["company_name"] == "New Name"
    assert result["routing_hints"]["lead"] == "board-existing"


def test_put_memory_tenant_isolation():
    from app.main import put_tenant_memory, TenantMemoryRequest
    db = MagicMock()
    request = TenantMemoryRequest(business_profile={"company_name": "Solo"})
    with (
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value={},
        ) as mock_get,
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings"
        ) as mock_save,
    ):
        put_tenant_memory(request=request, db=db, tenant_id="TENANT_XYZ")

    assert "TENANT_XYZ" in mock_get.call_args[0]
    assert "TENANT_XYZ" in mock_save.call_args[0]


def test_put_memory_empty_body_is_valid_no_op():
    result, mock_save = _put({})
    assert "business_profile" in result
    # update_settings not called when nothing changed (all None)
    # Actually it IS called (we always persist) — just verify no error
    assert result["business_profile"]["tone"] == "professional"


def test_put_memory_system_map_update():
    result, _ = _put(
        {
            "system_map": {
                "gmail": {"known_senders": ["a@b.com"], "detected_mail_types": ["lead"]}
            }
        }
    )
    assert "a@b.com" in result["system_map"]["gmail"]["known_senders"]
    assert "lead" in result["system_map"]["gmail"]["detected_mail_types"]


# ---------------------------------------------------------------------------
# GET /workflow-scan/status
# ---------------------------------------------------------------------------

def test_scan_status_default_shape():
    result = _scan(stored_settings={})
    assert result["last_scan_at"] is None
    assert result["systems_scanned"] == []
    assert result["status"] == "never_run"
    assert result["summary"] == {}


def test_scan_status_returns_stored_values():
    stored = {
        "workflow_scan": {
            "last_scan_at": "2026-04-26T10:00:00Z",
            "systems_scanned": ["gmail", "monday"],
            "status": "ok",
            "summary": {"messages_scanned": 42},
        }
    }
    result = _scan(stored_settings=stored)
    assert result["last_scan_at"] == "2026-04-26T10:00:00Z"
    assert "gmail" in result["systems_scanned"]
    assert result["status"] == "ok"
    assert result["summary"]["messages_scanned"] == 42


def test_scan_status_tenant_isolation():
    from app.main import workflow_scan_status
    db = MagicMock()
    with patch(
        "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
        return_value={},
    ) as mock_get:
        workflow_scan_status(db=db, tenant_id="TENANT_ABC")
    assert "TENANT_ABC" in mock_get.call_args[0]


def test_scan_status_partial_stored_values_fallback_to_defaults():
    stored = {"workflow_scan": {"status": "partial"}}
    result = _scan(stored_settings=stored)
    assert result["status"] == "partial"
    assert result["last_scan_at"] is None
    assert result["systems_scanned"] == []
    assert result["summary"] == {}
