"""Centralized secret leak scan (Kapitel 11)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Context-aware patterns — avoid bare "password" field names.
SECRET_PATTERNS = [
    re.compile(r'"access_token"\s*:\s*"[A-Za-z0-9._\-]{20,}"'),
    re.compile(r'"refresh_token"\s*:\s*"[A-Za-z0-9._\-]{20,}"'),
    re.compile(r'"client_secret"\s*:\s*"[A-Za-z0-9._\-]{8,}"'),
    re.compile(r'"api_key"\s*:\s*"[A-Za-z0-9_\-]{20,}"'),
    re.compile(r"sk-proj-[A-Za-z0-9]{10,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}"),
    re.compile(r"postgresql://[^\s\"']+:[^\s\"']+@"),
]


def _scan_text(text: str, label: str) -> list[str]:
    hits: list[str] = []
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            hits.append(f"{label}: matched {pattern.pattern}")
    return hits


@pytest.mark.parametrize(
    "rel_path",
    [
        "docs/security/kapitel-11-inventory.md",
        "frontend/README.md",
    ],
)
def test_docs_no_literal_secrets(rel_path):
    path = ROOT / rel_path
    if not path.is_file():
        pytest.skip(f"{rel_path} missing")
    hits = _scan_text(path.read_text(encoding="utf-8"), rel_path)
    assert not hits, hits


def test_frontend_src_no_local_storage_secrets():
    src = ROOT / "frontend" / "src"
    if not src.is_dir():
        pytest.skip("frontend/src missing")
    hits: list[str] = []
    for path in src.rglob("*.{ts,tsx,js,jsx}"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "localStorage" in text or "sessionStorage" in text:
            hits.append(str(path.relative_to(ROOT)))
    assert not hits, f"Browser storage usage found: {hits}"


def test_kapitel10_e2e_report_if_present_no_secrets():
    report = ROOT / "scripts" / "kapitel10_e2e_report.json"
    if not report.is_file():
        pytest.skip("no e2e report")
    text = report.read_text(encoding="utf-8")
    hits = _scan_text(text, "kapitel10_e2e_report.json")
    assert not hits, hits
    # sanity: valid json
    json.loads(text)
