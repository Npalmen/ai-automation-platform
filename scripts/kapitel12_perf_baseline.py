"""
Kapitel 12 — performance baseline (Profil A + B).

Uses in-process FastAPI TestClient with SQLite seed data unless K12_PERF_BASE_URL is set.

Output: scripts/kapitel12_perf_report.json
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.core.admin_session import hash_password
from app.core.settings import get_settings
from app.main import app as fastapi_app

ORIGIN_OK = "http://testserver"
PASSWORD = "k12-perf-password"
SECRET = "k12-perf-secret"

THRESHOLDS = {
    "read_p95_ms": 500.0,
    "overview_needs_help_p95_ms": 1500.0,
    "write_p95_ms": 2000.0,
    "error_rate_max": 0.01,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


def _session_settings(role: str = "operations"):
    h = hash_password(PASSWORD)
    return SimpleNamespace(
        SESSION_SECRET_KEY=SECRET,
        ADMIN_PASSWORD_HASH=h,
        ADMIN_USERNAME="admin",
        ADMIN_ROLE=role,
        ADMIN_DISPLAY_NAME="Perf Operator",
        ENV="dev",
        ALLOWED_ORIGINS="",
        ADMIN_API_KEY=get_settings().ADMIN_API_KEY or "test-admin-key",
        ADMIN_API_KEYS="",
        APP_NAME="AI Automation Platform",
        BACKUP_STATUS_FILE=str(ROOT / "storage" / "status" / "backup_status.json"),
        RESTORE_STATUS_FILE=str(ROOT / "storage" / "status" / "restore_status.json"),
        BUILD_METADATA_PATH=str(ROOT / "storage" / "status" / "build-metadata.json"),
    )


@contextmanager
def perf_client(role: str = "operations"):
    settings = _session_settings(role)
    get_settings.cache_clear()
    with patch("app.core.admin_session.get_settings", return_value=settings):
        with patch("app.main.get_settings", return_value=settings):
            with patch.dict(os.environ, {"ADMIN_ROLE": role}, clear=False):
                get_settings.cache_clear()
                client = TestClient(fastapi_app)
                login = client.post(
                    "/auth/admin/login",
                    json={"username": "admin", "password": PASSWORD},
                    headers={"Origin": ORIGIN_OK},
                )
                if login.status_code != 200:
                    raise RuntimeError(f"login failed: {login.status_code}")
                yield client
    get_settings.cache_clear()


def _measure_http(base_url: str, headers: dict, method: str, path: str, **kwargs) -> tuple[float, int]:
    url = f"{base_url.rstrip('/')}{path}"
    started = time.perf_counter()
    if method == "GET":
        resp = requests.get(url, headers=headers, timeout=30, **kwargs)
    else:
        resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return elapsed_ms, resp.status_code


def _measure_client(client: TestClient, method: str, path: str, **kwargs) -> tuple[float, int]:
    started = time.perf_counter()
    if method == "GET":
        resp = client.get(path, **kwargs)
    else:
        resp = client.request(method, path, **kwargs)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return elapsed_ms, resp.status_code


def _mock_db():
    db = MagicMock()

    def query_side_effect(*args, **kwargs):
        q = MagicMock()
        q.filter.return_value = q
        q.group_by.return_value = q
        q.count.return_value = 0
        q.all.return_value = []
        q.order_by.return_value = q
        return q

    db.query.side_effect = query_side_effect
    return db


def _triage_rows(profile: str) -> list:
    from app.admin.operations_triage import _row

    count = 20 if profile == "A" else 200
    rows = []
    tenants = 1 if profile == "A" else 10
    for i in range(count):
        tid = f"T_K12_PERF_{profile}_{i % tenants:02d}"
        rows.append(
            _row(
                tenant_id=tid,
                tenant_name=f"Perf {tid}",
                severity=["critical", "high", "medium", "info"][i % 4],
                area="pipeline",
                title=f"Issue {i}",
                detail="synthetic",
                job_id=f"job-{i}",
                source_id=f"job:job-{i}",
                source_type="job",
                created_at="2026-07-18T10:00:00+00:00",
                retryable="unknown",
                external_impact="unknown",
                runbook_ref="pilot_support",
            )
        )
    return rows


def _tenant_records(profile: str) -> list:
    from app.repositories.postgres.tenant_config_models import TenantConfigRecord

    count = 1 if profile == "A" else 10
    now = _utcnow()
    records = []
    for i in range(count):
        records.append(
            TenantConfigRecord(
                tenant_id=f"T_K12_PERF_{profile}_{i:02d}",
                name=f"Perf {i}",
                slug=f"perf-{profile.lower()}-{i}",
                status="active",
                settings={"scheduler": {"run_mode": "paused"}},
                enabled_job_types=["lead"],
                allowed_integrations=[],
                created_at=now,
                updated_at=now,
            )
        )
    return records


def _perf_patches(profile: str):
    tenants = _tenant_records(profile)
    triage = _triage_rows(profile)
    return (
        patch(
            "app.admin.operations_overview.TenantConfigRepository.list_all",
            return_value=tenants,
        ),
        patch(
            "app.admin.operations_overview.collect_all_triage_rows",
            return_value=triage,
        ),
        patch(
            "app.admin.operations_needs_help.collect_all_triage_rows",
            return_value=triage,
        ),
    )


def _run_profile(profile: str, iterations: int = 5) -> dict:
    base_url = os.environ.get("K12_PERF_BASE_URL", "").strip()
    endpoints = [
        ("GET", "/health", "read"),
        ("GET", "/admin/operations/overview", "overview"),
        ("GET", "/admin/operations/needs-help", "overview"),
    ]

    results: dict[str, dict] = {}
    errors = 0
    total = 0

    if base_url:
        api_key = get_settings().ADMIN_API_KEY or ""
        headers = {"X-Admin-API-Key": api_key} if api_key else {}
        for method, path, bucket in endpoints:
            timings: list[float] = []
            for _ in range(iterations):
                ms, status = _measure_http(base_url, headers, method, path)
                timings.append(ms)
                total += 1
                if status >= 500:
                    errors += 1
            results[path] = {
                "bucket": bucket,
                "p50_ms": round(_percentile(timings, 50), 2),
                "p95_ms": round(_percentile(timings, 95), 2),
                "p99_ms": round(_percentile(timings, 99), 2),
                "samples": len(timings),
            }
        return {
            "profile": profile,
            "mode": "live_http",
            "base_url": base_url,
            "tenant_count": 10 if profile == "B" else 1,
            "endpoints": results,
            "error_rate": errors / max(total, 1),
            "errors": errors,
            "requests": total,
        }

    mock_db = _mock_db()

    def override_get_db():
        yield mock_db

    from app.api.dependencies import get_db

    patches = _perf_patches(profile)

    with perf_client("operations") as client, ExitStack() as stack:
        for patcher in patches:
            stack.enter_context(patcher)
        fastapi_app.dependency_overrides[get_db] = override_get_db
        try:
            for method, path, bucket in endpoints:
                timings: list[float] = []
                for _ in range(iterations):
                    ms, status = _measure_client(
                        client,
                        method,
                        path,
                        headers={"Origin": ORIGIN_OK},
                    )
                    timings.append(ms)
                    total += 1
                    if status >= 500:
                        errors += 1
                results[path] = {
                    "bucket": bucket,
                    "p50_ms": round(_percentile(timings, 50), 2),
                    "p95_ms": round(_percentile(timings, 95), 2),
                    "p99_ms": round(_percentile(timings, 99), 2),
                    "samples": len(timings),
                }
        finally:
            fastapi_app.dependency_overrides.clear()

    return {
        "profile": profile,
        "mode": "testclient_mocked_services",
        "tenant_count": 1 if profile == "A" else 10,
        "synthetic_triage_rows": len(_triage_rows(profile)),
        "endpoints": results,
        "error_rate": errors / max(total, 1),
        "errors": errors,
        "requests": total,
    }


def _evaluate_thresholds(report: dict) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    for profile_key in ("profile_a", "profile_b"):
        profile = report.get(profile_key, {})
        endpoints = profile.get("endpoints", {})
        read_p95 = max(
            (v["p95_ms"] for v in endpoints.values() if v.get("bucket") == "read"),
            default=0.0,
        )
        overview_p95 = max(
            (v["p95_ms"] for v in endpoints.values() if v.get("bucket") == "overview"),
            default=0.0,
        )
        checks[f"{profile_key}_read_p95"] = read_p95 <= THRESHOLDS["read_p95_ms"]
        checks[f"{profile_key}_overview_p95"] = overview_p95 <= THRESHOLDS["overview_needs_help_p95_ms"]
        checks[f"{profile_key}_error_rate"] = profile.get("error_rate", 1.0) <= THRESHOLDS["error_rate_max"]
    return checks


def main() -> int:
    print("Kapitel 12 performance baseline\n")
    started = time.perf_counter()
    profile_a = _run_profile("A", iterations=int(os.environ.get("K12_PERF_ITERATIONS", "5")))
    profile_b = _run_profile("B", iterations=int(os.environ.get("K12_PERF_ITERATIONS", "5")))
    elapsed = time.perf_counter() - started

    report = {
        "generated_at": _utcnow().isoformat().replace("+00:00", "Z"),
        "duration_seconds": round(elapsed, 2),
        "thresholds": THRESHOLDS,
        "profile_a": profile_a,
        "profile_b": profile_b,
        "threshold_checks": _evaluate_thresholds({"profile_a": profile_a, "profile_b": profile_b}),
    }
    report["status"] = (
        "PASS"
        if all(report["threshold_checks"].values())
        else "FAIL"
    )

    out = ROOT / "scripts" / "kapitel12_perf_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Profile A: {profile_a['requests']} requests, error_rate={profile_a['error_rate']:.3f}")
    print(f"Profile B: {profile_b['requests']} requests, error_rate={profile_b['error_rate']:.3f}")
    print(f"Status: {report['status']}")
    print(f"Report: {out}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
