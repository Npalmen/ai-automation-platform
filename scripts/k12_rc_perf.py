#!/usr/bin/env python3
"""Live perf with strict status checks + host/container metrics."""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ENV_FILE = Path("/opt/krowolf/.env.production")
BASE = "https://api.krowolf.se"
ITERATIONS = int(__import__("os").environ.get("K12_PERF_ITERATIONS", "10"))
THRESHOLDS = {"read_p95_ms": 500.0, "overview_p95_ms": 1500.0, "error_rate_max": 0.01}

ENDPOINTS = [
    ("/health", "read", {"status"}),
    ("/admin/operations/overview", "overview", {"platform_status", "counters"}),
    ("/admin/operations/needs-help", "overview", {"items"}),
    ("/admin/system/status", "overview", {"overall_status", "runtime"}),
]


def _admin_key() -> str:
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("ADMIN_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


def _measure(path: str, headers: dict) -> tuple[float, int, bool]:
    req = Request(f"{BASE}{path}", headers=headers, method="GET")
    started = time.perf_counter()
    schema_ok = False
    try:
        with urlopen(req, timeout=30) as resp:
            status = resp.status
            body = json.loads(resp.read().decode("utf-8"))
            required = next((r for p, _, r in ENDPOINTS if p == path), set())
            schema_ok = isinstance(body, dict) and required.issubset(body.keys())
    except HTTPError as exc:
        status = exc.code
    except Exception:
        status = 0
    elapsed = (time.perf_counter() - started) * 1000.0
    return elapsed, int(status), schema_ok


def _host_metrics() -> dict:
    def sh(cmd: str) -> str:
        return subprocess.check_output(cmd, shell=True, text=True).strip()

    cpu = sh("top -bn1 | awk '/^%Cpu/{print $2}'")
    mem = sh("free -m | awk '/^Mem:/{print $3\"MB used / \"$2\"MB total\"}'")
    db_conns = sh(
        "sudo docker exec krowolf-db-1 psql -U postgres -d ai_platform -tAc "
        "\"SELECT count(*) FROM pg_stat_activity WHERE datname='ai_platform';\""
    )
    stats = sh("sudo docker stats --no-stream --format '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}' krowolf-app-1 krowolf-db-1 2>/dev/null")
    containers = []
    for line in stats.splitlines():
        parts = line.split("|")
        if len(parts) == 3:
            containers.append({"name": parts[0], "cpu": parts[1], "memory": parts[2]})
    return {"host_cpu_percent": cpu, "host_memory": mem, "db_connections": int(db_conns or 0), "containers": containers}


def _run_profile(name: str, headers: dict) -> dict:
    results = {}
    errors = 0
    total = 0
    for path, bucket, _required in ENDPOINTS:
        timings: list[float] = []
        for _ in range(ITERATIONS):
            ms, status, schema_ok = _measure(path, headers)
            timings.append(ms)
            total += 1
            if status != 200 or not schema_ok:
                errors += 1
        results[path] = {
            "bucket": bucket,
            "p50_ms": round(_percentile(timings, 50), 2),
            "p95_ms": round(_percentile(timings, 95), 2),
            "p99_ms": round(_percentile(timings, 99), 2),
            "samples": len(timings),
        }
    return {"profile": name, "endpoints": results, "error_rate": errors / max(total, 1), "requests": total}


def main() -> int:
    key = _admin_key()
    headers = {"X-Admin-API-Key": key} if key else {}
    metrics_before = _host_metrics()
    started = time.perf_counter()
    profile_a = _run_profile("A", headers)
    profile_b = _run_profile("B", headers)
    metrics_after = _host_metrics()
    duration = round(time.perf_counter() - started, 2)

    checks = {}
    for key_name, prof in ("profile_a", profile_a), ("profile_b", profile_b):
        eps = prof["endpoints"]
        read_p95 = max((v["p95_ms"] for v in eps.values() if v["bucket"] == "read"), default=0.0)
        ov_p95 = max((v["p95_ms"] for v in eps.values() if v["bucket"] == "overview"), default=0.0)
        checks[f"{key_name}_read_p95"] = read_p95 <= THRESHOLDS["read_p95_ms"]
        checks[f"{key_name}_overview_p95"] = ov_p95 <= THRESHOLDS["overview_p95_ms"]
        checks[f"{key_name}_error_rate"] = prof["error_rate"] <= THRESHOLDS["error_rate_max"]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "base_url": BASE,
        "duration_seconds": duration,
        "thresholds": THRESHOLDS,
        "metrics_before": metrics_before,
        "metrics_after": metrics_after,
        "profile_a": profile_a,
        "profile_b": profile_b,
        "threshold_checks": checks,
        "status": "PASS" if all(checks.values()) else "FAIL",
    }
    out = Path("/tmp/k12_rc_perf_report.json")
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "threshold_checks": checks, "metrics_after": metrics_after}, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
