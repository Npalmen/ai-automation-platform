"""
Tests for GET /tenants — DB-backed tenant listing endpoint.

Covers:
  - Response shape: {items, total}
  - Returns only DB-backed tenants (no static/fallback tenants)
  - Empty DB returns empty list with total 0
  - Single tenant returns correct fields (tenant_id, name)
  - Multiple tenants all appear in response
  - list_all() repository method works correctly

Tests call the endpoint function directly with mocked DB sessions,
matching the established pattern in this repo.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_record(tenant_id: str, name: str | None = None) -> MagicMock:
    record = MagicMock()
    record.tenant_id = tenant_id
    record.name = name
    return record


def _call_list_tenants(records: list) -> dict:
    from app.main import list_tenants
    db = MagicMock()
    with patch(
        "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.list_all",
        return_value=records,
    ):
        return list_tenants(db=db)


# ---------------------------------------------------------------------------
# GET /tenants — response shape
# ---------------------------------------------------------------------------

class TestListTenantsShape:
    def test_returns_items_key(self):
        result = _call_list_tenants([])
        assert "items" in result

    def test_returns_total_key(self):
        result = _call_list_tenants([])
        assert "total" in result

    def test_empty_db_returns_empty_items(self):
        result = _call_list_tenants([])
        assert result["items"] == []

    def test_empty_db_total_is_zero(self):
        result = _call_list_tenants([])
        assert result["total"] == 0

    def test_single_tenant_total_is_one(self):
        result = _call_list_tenants([_mock_record("TENANT_A", "Alpha")])
        assert result["total"] == 1

    def test_multiple_tenants_total_matches_count(self):
        records = [
            _mock_record("TENANT_A", "Alpha"),
            _mock_record("TENANT_B", "Beta"),
            _mock_record("TENANT_C", "Gamma"),
        ]
        result = _call_list_tenants(records)
        assert result["total"] == 3
        assert len(result["items"]) == 3


# ---------------------------------------------------------------------------
# GET /tenants — item fields
# ---------------------------------------------------------------------------

class TestListTenantsFields:
    def test_item_contains_tenant_id(self):
        result = _call_list_tenants([_mock_record("TENANT_X")])
        assert result["items"][0]["tenant_id"] == "TENANT_X"

    def test_item_contains_name(self):
        result = _call_list_tenants([_mock_record("TENANT_X", "X Corp")])
        assert result["items"][0]["name"] == "X Corp"

    def test_item_name_can_be_none(self):
        result = _call_list_tenants([_mock_record("TENANT_Y", None)])
        assert result["items"][0]["name"] is None

    def test_all_tenant_ids_present(self):
        records = [_mock_record(f"TENANT_{i}") for i in range(5)]
        result = _call_list_tenants(records)
        ids = {item["tenant_id"] for item in result["items"]}
        assert ids == {f"TENANT_{i}" for i in range(5)}


# ---------------------------------------------------------------------------
# GET /tenants — only DB tenants (no fallback/static pollution)
# ---------------------------------------------------------------------------

class TestListTenantsNoBallback:
    def test_only_returns_what_list_all_provides(self):
        """If list_all returns an empty list, /tenants must return empty — no static tenants."""
        result = _call_list_tenants([])
        assert result["items"] == []
        assert result["total"] == 0

    def test_does_not_include_tenants_not_in_list_all(self):
        """Only tenants explicitly returned by list_all appear in the response."""
        result = _call_list_tenants([_mock_record("TENANT_REAL")])
        ids = [item["tenant_id"] for item in result["items"]]
        assert ids == ["TENANT_REAL"]


# ---------------------------------------------------------------------------
# TenantConfigRepository.list_all — unit test
# ---------------------------------------------------------------------------

class TestTenantConfigRepositoryListAll:
    def test_list_all_queries_tenant_config_record(self):
        from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
        from app.repositories.postgres.tenant_config_models import TenantConfigRecord

        db = MagicMock()
        fake_records = [_mock_record("TENANT_A"), _mock_record("TENANT_B")]
        (
            db.query.return_value
               .order_by.return_value
               .all.return_value
        ) = fake_records

        result = TenantConfigRepository.list_all(db)

        db.query.assert_called_once_with(TenantConfigRecord)
        assert result == fake_records

    def test_list_all_returns_empty_list_when_no_rows(self):
        from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

        db = MagicMock()
        db.query.return_value.order_by.return_value.all.return_value = []

        result = TenantConfigRepository.list_all(db)
        assert result == []
