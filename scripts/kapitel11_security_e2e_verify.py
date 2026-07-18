"""Kapitel 11 security E2E verification (local)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.core.settings import get_settings

BASE = "http://127.0.0.1:8000"
ORIGIN = "http://localhost:5173"


def main() -> int:
    settings = get_settings()
    api_key = settings.ADMIN_API_KEY.strip()
    if not api_key:
        print("SKIP: ADMIN_API_KEY not set")
        return 0

    h = {"X-Admin-API-Key": api_key, "Origin": ORIGIN}
    checks: list[dict] = []

    def ok(name: str, detail: str = ""):
        checks.append({"name": name, "status": "PASS", "detail": detail})
        print(f"PASS {name}" + (f" — {detail}" if detail else ""))

    def fail(name: str, detail: str):
        checks.append({"name": name, "status": "FAIL", "detail": detail})
        print(f"FAIL {name} — {detail}")

    health = requests.get(f"{BASE}/health", timeout=10)
    if health.status_code == 200:
        ok("stack.health")
    else:
        fail("stack.health", str(health.status_code))

    headers = requests.get(f"{BASE}/health", timeout=10).headers
    if headers.get("X-Content-Type-Options") == "nosniff":
        ok("headers.nosniff")
    else:
        fail("headers.nosniff", str(headers.get("X-Content-Type-Options")))

    get_run = requests.get(f"{BASE}/admin/alerts/run-all", headers=h, timeout=30)
    if get_run.status_code == 405:
        ok("security.no_get_run_all")
    else:
        fail("security.no_get_run_all", str(get_run.status_code))

    post_run = requests.post(f"{BASE}/admin/alerts/run-all", headers=h, timeout=120)
    if post_run.status_code == 200:
        ok("security.post_run_all")
    else:
        fail("security.post_run_all", str(post_run.status_code))

    out = ROOT / "scripts" / "kapitel11_security_e2e_report.json"
    out.write_text(json.dumps({"checks": checks}, indent=2), encoding="utf-8")
    print(f"\nReport: {out}")
    return 1 if any(c["status"] == "FAIL" for c in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
