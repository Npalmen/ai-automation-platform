#!/usr/bin/env python3
"""Slice C Commit 4 — customer settings API + optional browser smoke gate."""

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
DEFAULT_REPORT = ROOT / "storage" / "customer_settings_browser_smoke_report.json"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    data = None
    req_headers = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=req_headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw or "{}")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError:
            payload = {"detail": raw}
        return exc.code, payload
    except URLError as exc:
        return 0, {"detail": str(exc)}


class Recorder:
    def __init__(self) -> None:
        self.checks: list[dict[str, str]] = []

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        status = "PASS" if ok else "FAIL"
        self.checks.append({"name": name, "status": status, "detail": detail})
        print(f"{status} {name}" + (f" — {detail}" if detail else ""))

    @property
    def passed(self) -> int:
        return sum(1 for item in self.checks if item["status"] == "PASS")

    @property
    def failed(self) -> int:
        return sum(1 for item in self.checks if item["status"] == "FAIL")


def run_api_smoke(
    *,
    backend_url: str,
    frontend_url: str,
    tenant_id: str,
    admin_api_key: str,
) -> Recorder:
    rec = Recorder()
    backend = backend_url.rstrip("/")
    frontend = frontend_url.rstrip("/")
    headers = {"X-Admin-API-Key": admin_api_key, "Origin": frontend}

    status, health = _request("GET", f"{backend}/")
    rec.add("backend health", status == 200 and health.get("status") == "ok", f"status={status}")

    status, aggregate = _request("GET", f"{backend}/admin/tenants/{tenant_id}/settings", headers=headers)
    rec.add(
        "aggregate GET",
        status == 200 and aggregate.get("tenant_id") == tenant_id,
        f"status={status}",
    )

    for domain in ("identity", "modules", "integrations", "routing", "automation"):
        dstatus, _ = _request(
            "GET",
            f"{backend}/admin/tenants/{tenant_id}/settings/{domain}",
            headers=headers,
        )
        rec.add(f"domain GET {domain}", dstatus == 200, f"status={dstatus}")

    pstatus, preview = _request(
        "POST",
        f"{backend}/admin/tenants/{tenant_id}/settings/routing/preview",
        headers=headers,
        body={"payload": {"routing": {"route_overrides": {"invoice_generic": "finance"}}}},
    )
    rec.add(
        "routing preview",
        pstatus == 200 and preview.get("valid") is True,
        f"status={pstatus}",
    )

    version = int(aggregate.get("config_version") or 0)
    cstatus, conflict = _request(
        "PATCH",
        f"{backend}/admin/tenants/{tenant_id}/settings/identity",
        headers=headers,
        body={"expected_config_version": version + 999, "payload": {"timezone": "Europe/Stockholm"}},
    )
    rec.add("stale PATCH 409", cstatus == 409, f"status={cstatus}, detail={conflict}")

    # frontend shell
    fstatus, _ = _request("GET", f"{frontend}/ops/")
    rec.add("frontend /ops shell", fstatus == 200, f"status={fstatus}")
    settings_url = f"{frontend}/ops/customers/{tenant_id}/settings?tab=integrations"
    sstatus, _ = _request("GET", settings_url)
    rec.add("frontend settings route shell", sstatus == 200, f"status={sstatus}, url={settings_url}")

    readiness = aggregate.get("effective_readiness") or {}
    blockers = readiness.get("blockers") or []
    if blockers:
        action_domain = blockers[0].get("action_domain")
        rec.add(
            "readiness blocker action_domain present",
            bool(action_domain),
            str(action_domain or ""),
        )
    else:
        rec.add("readiness blocker action_domain present", True, "no blockers")

    permissions = aggregate.get("permissions") or {}
    rec.add(
        "permissions routing write for admin",
        bool((permissions.get("routing") or {}).get("write")),
        str(permissions.get("routing")),
    )
    rec.add(
        "scheduler read-only in aggregate",
        "scheduler" not in str((aggregate.get("domains") or {}).get("automation") or {}),
        "automation domain uses policy only",
    )
    return rec


def main() -> int:
    parser = argparse.ArgumentParser(description="Customer settings browser/API smoke gate")
    parser.add_argument("--backend-url", default=os.getenv("SMOKE_BACKEND_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--frontend-url", default=os.getenv("SMOKE_FRONTEND_URL", "http://127.0.0.1:5173"))
    parser.add_argument("--tenant-id", default=os.getenv("SMOKE_TENANT_ID", "T_NIKLAS_DEMO_001"))
    parser.add_argument("--admin-api-key", default=os.getenv("ADMIN_API_KEY", ""))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    args = parser.parse_args()

    if not args.admin_api_key:
        print("ERR ADMIN_API_KEY required for smoke gate", file=sys.stderr)
        return 2

    rec = run_api_smoke(
        backend_url=args.backend_url,
        frontend_url=args.frontend_url,
        tenant_id=args.tenant_id,
        admin_api_key=args.admin_api_key,
    )
    report = {
        "generated_at": _utcnow(),
        "backend_url": args.backend_url,
        "frontend_url": args.frontend_url,
        "tenant_id": args.tenant_id,
        "passed": rec.passed,
        "failed": rec.failed,
        "checks": rec.checks,
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report: {report_path}")
    return 0 if rec.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
