"""Config snapshot contract tests."""

from __future__ import annotations

from app.production_pilot.config_snapshot import (
    build_snapshot_record,
    compute_snapshot_hash,
    restore_snapshot_payload,
    verify_snapshot_hash,
)
from app.production_pilot.kill_switches import apply_p0_baseline


def test_snapshot_restore_hash_match():
    settings = apply_p0_baseline()
    snapshot = build_snapshot_record(settings)
    assert verify_snapshot_hash(snapshot)
    restored = restore_snapshot_payload(snapshot)
    assert compute_snapshot_hash(restored) == snapshot["snapshot_hash"]
