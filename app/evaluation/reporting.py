"""JSON and terminal reporting for evaluation harness."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HARNESS_VERSION = "2d.0.0"


@dataclass
class ScenarioResult:
    scenario_id: str
    status: str
    safety_passed: bool
    safety_violations: list[str] = field(default_factory=list)
    quality_metrics: dict[str, Any] = field(default_factory=dict)
    diagnostic_score: float | None = None
    duration_ms: int = 0
    exit_code: int = 0
    regression: dict[str, Any] = field(default_factory=dict)


@dataclass
class HarnessRunResult:
    run_id: str
    scenarios: list[ScenarioResult] = field(default_factory=list)
    exit_code: int = 0
    mode: str = "deterministic"
    baseline_id: str | None = None

    @property
    def summary(self) -> dict[str, Any]:
        passed = sum(1 for s in self.scenarios if s.status == "pass")
        return {
            "total": len(self.scenarios),
            "passed": passed,
            "failed": len(self.scenarios) - passed,
            "regressions": sum(1 for s in self.scenarios if s.regression.get("is_regression")),
        }


def render_terminal(result: HarnessRunResult) -> str:
    lines = [
        "Kapitel 2D Evaluation Harness — deterministic",
        f"Run: {result.run_id}  baseline:{result.baseline_id or 'none'}",
        "",
        f"RESULT  {result.summary['passed']}/{result.summary['total']} passed  "
        f"{result.summary['failed']} failed  ({result.summary['regressions']} regressions)",
        "",
        "METRICS",
    ]
    agg: dict[str, dict] = {}
    for sc in result.scenarios:
        for name, m in (sc.quality_metrics or {}).items():
            bucket = agg.setdefault(name, {"passed": 0, "total": 0})
            bucket["passed"] += m.get("passed", 0)
            bucket["total"] += m.get("total", 0)
    for name, bucket in sorted(agg.items()):
        total = bucket["total"] or 1
        pct = 100.0 * bucket["passed"] / total
        lines.append(f"  {name:30} {bucket['passed']}/{bucket['total']}  {pct:5.1f}%")
    failures = [s for s in result.scenarios if s.status != "pass"]
    if failures:
        lines.append("")
        lines.append("FAILURES")
        for sc in failures[:10]:
            lines.append(f"  {sc.scenario_id} exit={sc.exit_code} {sc.safety_violations}")
    return "\n".join(lines)


def write_json_report(result: HarnessRunResult, path: Path) -> None:
    payload = {
        "harness_version": HARNESS_VERSION,
        "run_id": result.run_id,
        "mode": result.mode,
        "baseline_id": result.baseline_id,
        "summary": result.summary,
        "exit_code": result.exit_code,
        "scenarios": [
            {
                "scenario_id": s.scenario_id,
                "status": s.status,
                "safety_passed": s.safety_passed,
                "safety_violations": s.safety_violations,
                "quality_metrics": s.quality_metrics,
                "diagnostic_score": s.diagnostic_score,
                "duration_ms": s.duration_ms,
                "regression": s.regression,
                "exit_code": s.exit_code,
            }
            for s in result.scenarios
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
