"""Determinism and migration drift checks."""

from __future__ import annotations

from pathlib import Path

from app.evaluation.regression.constants import SEMANTIC_HASH_VERSION
from app.repositories.postgres.migration_runner import ORDERED_MIGRATION_FILES

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"


def validate_migration_registry() -> list[str]:
    failures: list[str] = []
    if not MIGRATIONS_DIR.is_dir():
        failures.append("migrations directory missing")
        return failures
    disk_files = sorted(path.name for path in MIGRATIONS_DIR.glob("*.sql"))
    ordered = list(ORDERED_MIGRATION_FILES)
    if disk_files != ordered:
        failures.append(
            f"migration files on disk {disk_files} do not match ordered registry {ordered}"
        )
    numbers = []
    for name in ordered:
        prefix = name.split("_", 1)[0]
        if not prefix.isdigit():
            failures.append(f"migration numbering invalid: {name}")
            continue
        numbers.append(int(prefix))
    if numbers != sorted(numbers):
        failures.append("migration numbering is not monotonic")
    if len(numbers) != len(set(numbers)):
        failures.append("duplicate migration numbers detected")
    return failures


def validate_semantic_hash_version(expected_version: str | None = None) -> list[str]:
    version = expected_version or SEMANTIC_HASH_VERSION
    if version != SEMANTIC_HASH_VERSION:
        return [f"semantic hash version drift: expected {SEMANTIC_HASH_VERSION}, got {version}"]
    return []


def validate_repeat_run_hashes(hashes1: dict[str, str], hashes2: dict[str, str]) -> list[str]:
    failures: list[str] = []
    for key in sorted(hashes1):
        if hashes1.get(key) != hashes2.get(key):
            failures.append(f"determinism drift for {key}")
    return failures
