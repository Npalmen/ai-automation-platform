#!/usr/bin/env python3
"""Slice C Commit 4 — post-smoke side-effect gate for customer settings."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "storage" / "customer_settings_side_effect_gate_report.json"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_json(url: str, headers: dict[str, str]) -> tuple[int, Any]:
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read().decode("utf-8") or "{}")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(raw or "{}")
        except json.JSONDecodeError:
            return exc.code, {"detail": raw}
    except URLError as exc:
        return 0, {"detail": str(exc)}


def snapshot(backend_url: str, tenant_id: str, admin_api_key: str) -> dict[str, Any]:
    headers = {"X-Admin-API-Key": admin_api_key}
    base = backend_url.rstrip("/")
    _, settings = _get_json(f"{base}/admin/tenants/{tenant_id}/settings", headers)
    _, health = _get_json(f"{base}/admin/tenants/{tenant_id}/health", headers)
    return {
        "config_version": settings.get("config_version"),
        "scheduler_run_mode": (settings.get("automation_policy_summary") or {}).get("scheduler_run_mode"),
        "enabled_external_writes": (settings.get("automation_policy_summary") or {}).get(
            "enabled_external_writes"
        ),
        "auto_actions": (settings.get("automation_policy_summary") or {}).get("auto_actions"),
        "health": health,
    }


def compare(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    add(
        "scheduler unchanged",
        before.get("scheduler_run_mode") == after.get("scheduler_run_mode"),
        f"{before.get('scheduler_run_mode')} -> {after.get('scheduler_run_mode')}",
    )
    add(
        "enabled_external_writes unchanged",
        before.get("enabled_external_writes") == after.get("enabled_external_writes"),
        str(after.get("enabled_external_writes")),
    )
    add(
        "auto_actions unchanged unless explicit settings patch",
        before.get("auto_actions") == after.get("auto_actions"),
        "projection read-only in smoke",
    )
    add(
        "config_version monotonic or unchanged",
        (after.get("config_version") or 0) >= (before.get("config_version") or 0),
        f"{before.get('config_version')} -> {after.get('config_version')}",
    )
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Customer settings side-effect gate")
    parser.add_argument("--backend-url", default=os.getenv("SMOKE_BACKEND_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--tenant-id", default=os.getenv("SMOKE_TENANT_ID", "T_NIKLAS_DEMO_001"))
    parser.add_argument("--admin-api-key", default=os.getenv("ADMIN_API_KEY", ""))
    parser.add_argument("--before", required=True, help="Path to before snapshot JSON")
    parser.add_argument("--after", help="Optional after snapshot path; if omitted, fetch live")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    args = parser.parse_args()

    if not args.admin_api_key:
        print("ERR ADMIN_API_KEY required", file=sys.stderr)
        return 2

    before = json.loads(Path(args.before).read_text(encoding="utf-8"))
    if args.after:
        after = json.loads(Path(args.after).read_text(encoding="utf-8"))
    else:
        after = snapshot(args.backend_url, args.tenant_id, args.admin_api_key)

    checks = compare(before, after)
    failed = sum(1 for item in checks if item["status"] == "FAIL")
    report = {
        "generated_at": _utcnow(),
        "tenant_id": args.tenant_id,
        "passed": len(checks) - failed,
        "failed": failed,
        "checks": checks,
        "before": before,
        "after": after,
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for item in checks:
        print(f"{item['status']} {item['name']}" + (f" — {item['detail']}" if item['detail'] else ""))
    print(f"Report: {report_path}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
