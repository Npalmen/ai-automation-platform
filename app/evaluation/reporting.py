"""JSON and terminal reporting for evaluation harness."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HARNESS_VERSION = "2e.0.0"


@dataclass
class ScenarioRuntimeObservation:
    """Per-run observations — not part of static gold scenario files."""

    llm_mode: str = "deterministic_fixture"
    model: str | None = None
    model_version: str | None = None
    gmail_message_id: str | None = None
    gmail_thread_id: str | None = None
    sent_at: str | None = None
    received_at: str | None = None
    run_id: str | None = None
    real_external_calls: int = 0
    fake_adapter_calls: int = 0
    execution_function_calls: int = 0


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
    runtime: ScenarioRuntimeObservation = field(default_factory=ScenarioRuntimeObservation)
    normalized_metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class HarnessRunResult:
    run_id: str
    scenarios: list[ScenarioResult] = field(default_factory=list)
    exit_code: int = 0
    mode: str = "deterministic"
    baseline_id: str | None = None
    dataset_id: str | None = None
    manifest_hash: str | None = None

    @property
    def summary(self) -> dict[str, Any]:
        passed = sum(1 for s in self.scenarios if s.status == "pass")
        return {
            "total": len(self.scenarios),
            "passed": passed,
            "failed": len(self.scenarios) - passed,
            "regressions": sum(1 for s in self.scenarios if s.regression.get("is_regression")),
            "real_external_calls": sum(s.runtime.real_external_calls for s in self.scenarios),
        }


def normalize_metrics_for_baseline(metrics: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for name, bucket in metrics.items():
        if isinstance(bucket, dict) and "score" in bucket:
            out[name] = round(float(bucket["score"]), 4)
    return out


def render_terminal(result: HarnessRunResult) -> str:
    lines = [
        "Kapitel 2E Evaluation Harness — deterministic",
        f"Run: {result.run_id}  baseline:{result.baseline_id or 'none'}  dataset:{result.dataset_id or 'none'}",
        "",
        f"RESULT  {result.summary['passed']}/{result.summary['total']} passed  "
        f"{result.summary['failed']} failed  ({result.summary['regressions']} regressions)  "
        f"real_external_calls={result.summary['real_external_calls']}",
        "",
        "METRICS",
    ]
    agg: dict[str, dict] = {}
    for sc in result.scenarios:
        for name, m in (sc.quality_metrics or {}).items():
            if not isinstance(m, dict) or "passed" not in m:
                continue
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
    if result.manifest_hash:
        lines.append("")
        lines.append(f"manifest_hash={result.manifest_hash}")
    return "\n".join(lines)


def write_json_report(result: HarnessRunResult, path: Path) -> None:
    payload = {
        "harness_version": HARNESS_VERSION,
        "run_id": result.run_id,
        "mode": result.mode,
        "baseline_id": result.baseline_id,
        "dataset_id": result.dataset_id,
        "manifest_hash": result.manifest_hash,
        "summary": result.summary,
        "exit_code": result.exit_code,
        "scenarios": [
            {
                "scenario_id": s.scenario_id,
                "status": s.status,
                "safety_passed": s.safety_passed,
                "safety_violations": s.safety_violations,
                "quality_metrics": s.quality_metrics,
                "normalized_metrics": s.normalized_metrics,
                "diagnostic_score": s.diagnostic_score,
                "duration_ms": s.duration_ms,
                "regression": s.regression,
                "exit_code": s.exit_code,
                "runtime": {
                    "llm_mode": s.runtime.llm_mode,
                    "model": s.runtime.model,
                    "model_version": s.runtime.model_version,
                    "gmail_message_id": s.runtime.gmail_message_id,
                    "gmail_thread_id": s.runtime.gmail_thread_id,
                    "sent_at": s.runtime.sent_at,
                    "received_at": s.runtime.received_at,
                    "run_id": s.runtime.run_id,
                    "real_external_calls": s.runtime.real_external_calls,
                    "fake_adapter_calls": s.runtime.fake_adapter_calls,
                    "execution_function_calls": s.runtime.execution_function_calls,
                },
            }
            for s in result.scenarios
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
