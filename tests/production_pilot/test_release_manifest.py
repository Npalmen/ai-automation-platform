"""Release manifest contract tests."""

from __future__ import annotations

from app.production_pilot.constants import PILOT_TENANT_ID, RELEASE_VERSION
from app.production_pilot.release_manifest import build_release_manifest, validate_release_manifest


def test_release_manifest_build_and_validate():
    manifest = build_release_manifest(activation_stage="P0", backup_reference="backup-test-001")
    failures = validate_release_manifest(manifest)
    assert failures == []
    assert manifest["release_version"] == RELEASE_VERSION
    assert manifest["pilot_tenant_id"] == PILOT_TENANT_ID
    assert manifest["activation_level"] == "P0"


def test_release_manifest_rejects_true_risk_flags(monkeypatch):
    manifest = build_release_manifest(backup_reference="backup-test-001")
    manifest["feature_flag_defaults"]["END_CUSTOMER_WRITE_API_ENABLED"] = True
    failures = validate_release_manifest(manifest)
    assert any("END_CUSTOMER_WRITE_API_ENABLED" in item for item in failures)
