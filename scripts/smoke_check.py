"""Run lightweight post-deploy smoke checks against a live platform URL."""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _request_json(url: str, *, headers: dict[str, str] | None = None) -> tuple[int, dict]:
    request = Request(url, headers=headers or {})
    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw or "{}")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError:
            payload = {"detail": raw}
        return exc.code, payload


def _check(condition: bool, message: str) -> bool:
    print(("OK  " if condition else "ERR ") + message)
    return condition


def main() -> int:
    parser = argparse.ArgumentParser(description="Post-deploy smoke check")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--admin-api-key", default="")
    parser.add_argument("--tenant-api-key", default="",
                        help="Tenant API key for authenticated smoke checks (optional).")
    parser.add_argument("--expect-production", action="store_true")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    ok = True

    try:
        status, payload = _request_json(f"{base_url}/")
    except (TimeoutError, URLError) as exc:
        print(f"ERR health endpoint unreachable: {exc}")
        return 1

    ok &= _check(status == 200, "GET / returns 200")
    ok &= _check(payload.get("status") == "ok", "health payload status is ok")

    if args.expect_production:
        docs_status, _ = _request_json(f"{base_url}/openapi.json")
        ok &= _check(docs_status == 404, "OpenAPI is not publicly exposed in production")

    if args.admin_api_key:
        admin_status, admin_payload = _request_json(
            f"{base_url}/admin/tenants/overview",
            headers={"X-Admin-API-Key": args.admin_api_key},
        )
        ok &= _check(admin_status == 200, "admin overview accepts ADMIN_API_KEY")
        ok &= _check("items" in admin_payload, "admin overview returns tenant items")

        needs_help_status, _ = _request_json(
            f"{base_url}/admin/operations/needs-help",
            headers={"X-Admin-API-Key": args.admin_api_key},
        )
        ok &= _check(needs_help_status == 200, "admin needs-help endpoint reachable")

    if args.tenant_api_key:
        tenant_headers = {"X-API-Key": args.tenant_api_key}

        health_status, health_payload = _request_json(
            f"{base_url}/integrations/health",
            headers=tenant_headers,
        )
        ok &= _check(health_status == 200, "tenant integration health endpoint reachable")
        ok &= _check("overall_status" in health_payload,
                     "integration health contains overall_status")

        sched_status, sched_payload = _request_json(
            f"{base_url}/scheduler/status",
            headers=tenant_headers,
        )
        ok &= _check(sched_status == 200, "tenant scheduler status endpoint reachable")
        ok &= _check("run_mode" in sched_payload, "scheduler status contains run_mode")

        readiness_status, readiness_payload = _request_json(
            f"{base_url}/pilot/readiness",
            headers=tenant_headers,
        )
        ok &= _check(readiness_status == 200, "pilot readiness endpoint reachable")
        ok &= _check("overall_status" in readiness_payload,
                     "pilot readiness contains overall_status")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
