#!/usr/bin/env python3
"""K12 RC endpoint verification — 404 or schema mismatch = FAIL."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path("/opt/krowolf")
ENV_FILE = ROOT / ".env.production"
BASE = "https://api.krowolf.se"


def _admin_key() -> str:
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("ADMIN_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _get(path: str, headers: dict | None = None) -> tuple[int, dict | str]:
    req = Request(f"{BASE}{path}", headers=headers or {}, method="GET")
    try:
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw[:500]


def _check(name: str, ok: bool, detail: str, results: list) -> None:
    status = "PASS" if ok else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})
    print(f"{status} {name}: {detail}")


def main() -> int:
    key = _admin_key()
    admin = {"X-Admin-API-Key": key} if key else {}
    results: list[dict] = []

    code, body = _get("/health")
    _check("health", code == 200 and isinstance(body, dict) and body.get("status") == "ok", f"http={code}", results)

    code, body = _get("/admin/operations/overview", admin)
    ok = code == 200 and isinstance(body, dict) and {"platform_status", "counters", "priorities"}.issubset(body.keys())
    _check("operations_overview", ok, f"http={code} keys={sorted(body.keys())[:10] if isinstance(body, dict) else type(body)}", results)

    code, body = _get("/admin/operations/needs-help", admin)
    ok = code == 200 and isinstance(body, dict) and "items" in body
    _check("needs_help", ok, f"http={code}", results)

    code, body = _get("/admin/system/status", admin)
    ok = code == 200 and isinstance(body, dict) and {"overall_status", "runtime", "resilience"}.issubset(body.keys())
    _check("system_status", ok, f"http={code} keys={sorted(body.keys())[:10] if isinstance(body, dict) else type(body)}", results)

    code, body = _get("/admin/alerts", admin)
    ok = code == 200 and isinstance(body, dict) and "items" in body
    _check("alerts", ok, f"http={code}", results)

    code, body = _get("/admin/alerts/summary", admin)
    ok = code == 200 and isinstance(body, dict)
    _check("alerts_summary", ok, f"http={code}", results)

    code, body = _get("/admin/onboarding/registries", admin)
    ok = code == 200 and isinstance(body, dict) and "registry_schema_version" in body
    _check("onboarding_registries", ok, f"http={code}", results)

    code, body = _get("/ui")
    ok = code == 200 and isinstance(body, str) and ("LEGACY_UI_READ_ONLY" in body or "legacy-ui-access" in body)
    _check("legacy_ui_readonly", ok, f"http={code} legacy_marker={'yes' if isinstance(body,str) and ('LEGACY_UI_READ_ONLY' in body or 'legacy-ui-access' in body) else 'no'}", results)

    fails = [r for r in results if r["status"] == "FAIL"]
    report = {"base_url": BASE, "checks": results, "status": "PASS" if not fails else "FAIL"}
    out = Path("/tmp/k12_rc_endpoint_report.json")
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report: {out}")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
