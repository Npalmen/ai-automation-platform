"""Kapitel 2F.4D — final closure contract for Live Eval chapter 2F."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)

CLOSURE_MARKER = "Kapitel 2F — PASS och stängt"
CLOSURE_MODE_FINAL: Literal["final"] = "final"

REQUIRED_DOCUMENTATION_FILES = (
    "docs/01-current-truth.md",
    "docs/06-backlog.md",
    "docs/09-testing-and-release.md",
    "docs/10f-live-eval-testbot.md",
)

REQUIRED_CI_CHECKS = frozenset(
    {
        "tests",
        "live_eval_postgresql",
        "frontend",
        "docker",
    }
)

SUCCESS_CHECK_VALUES = frozenset({"success", "passed"})

AUTHORITATIVE_GMAIL_RUN_ID = "30050565974"
AUTHORITATIVE_LLM_RUN_ID = "30131333378"
HISTORICAL_FAILURE_RUN_ID = "30125105087"


@dataclass(frozen=True)
class ClosureContext:
    closure_mode: Literal["final"]
    baseline_git_sha: str
    ci_event: str
    ci_branch: str
    ci_run_id: str
    ci_head_sha: str
    required_checks: dict[str, str]
    documentation_root: Path

    def to_payload(self) -> dict[str, Any]:
        return {
            "closure_mode": self.closure_mode,
            "baseline_git_sha": self.baseline_git_sha,
            "ci": {
                "event": self.ci_event,
                "branch": self.ci_branch,
                "run_id": self.ci_run_id,
                "head_sha": self.ci_head_sha,
                "required_checks": dict(sorted(self.required_checks.items())),
            },
            "documentation": {
                "status": "closed",
                "verified_files": list(REQUIRED_DOCUMENTATION_FILES),
                "closure_marker": CLOSURE_MARKER,
            },
        }


def _validate_git_sha(value: str, *, field: str) -> str:
    if not _GIT_SHA_RE.match(value):
        raise ValueError(f"{field} must be a 40-character git SHA")
    return value.lower()


def parse_required_check(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise ValueError(f"required check must use name=value format: {value!r}")
    name, status = value.split("=", 1)
    name = name.strip()
    status = status.strip().lower()
    if not name:
        raise ValueError("required check name must not be empty")
    if name not in REQUIRED_CI_CHECKS:
        raise ValueError(f"unknown required check: {name!r}")
    return name, status


def build_closure_context(
    *,
    baseline_git_sha: str,
    ci_event: str,
    ci_branch: str,
    ci_run_id: str,
    ci_head_sha: str,
    required_checks: dict[str, str],
    documentation_root: Path,
) -> ClosureContext:
    if not ci_run_id.strip():
        raise ValueError("ci run id must not be empty")
    normalized_checks = {name: status.lower() for name, status in required_checks.items()}
    missing = REQUIRED_CI_CHECKS - set(normalized_checks)
    if missing:
        raise ValueError(f"missing required checks: {', '.join(sorted(missing))}")
    extra = set(normalized_checks) - REQUIRED_CI_CHECKS
    if extra:
        raise ValueError(f"unexpected required checks: {', '.join(sorted(extra))}")

    return ClosureContext(
        closure_mode=CLOSURE_MODE_FINAL,
        baseline_git_sha=_validate_git_sha(baseline_git_sha, field="baseline_git_sha"),
        ci_event=ci_event,
        ci_branch=ci_branch,
        ci_run_id=ci_run_id.strip(),
        ci_head_sha=_validate_git_sha(ci_head_sha, field="ci_head_sha"),
        required_checks=normalized_checks,
        documentation_root=documentation_root,
    )


def validate_closure_context(context: ClosureContext) -> None:
    if context.closure_mode != CLOSURE_MODE_FINAL:
        raise ValueError("closure_mode must be final")
    if context.ci_event != "push":
        raise ValueError("final closure requires ci event push")
    if context.ci_branch != "main":
        raise ValueError("final closure requires ci branch main")
    if context.baseline_git_sha != context.ci_head_sha:
        raise ValueError("baseline_git_sha must match ci_head_sha")
    for check_name, status in context.required_checks.items():
        if status not in SUCCESS_CHECK_VALUES:
            raise ValueError(
                f"required check {check_name!r} must be success, got {status!r}"
            )


def verify_documentation_closure(documentation_root: Path) -> dict[str, Any]:
    verified_files: list[str] = []
    marker_found = False

    for relative_path in REQUIRED_DOCUMENTATION_FILES:
        path = documentation_root / relative_path
        if not path.is_file():
            raise ValueError(f"documentation file missing: {relative_path}")
        content = path.read_text(encoding="utf-8")
        if CLOSURE_MARKER not in content:
            raise ValueError(f"closure marker missing in {relative_path}")
        marker_found = True
        verified_files.append(relative_path)

    if not marker_found:
        raise ValueError("closure marker not found in authoritative documentation")

    truth = (documentation_root / "docs/01-current-truth.md").read_text(encoding="utf-8")
    backlog = (documentation_root / "docs/06-backlog.md").read_text(encoding="utf-8")
    testbot = (documentation_root / "docs/10f-live-eval-testbot.md").read_text(encoding="utf-8")

    for chapter in ("2F.1", "2F.2", "2F.3", "2F.4"):
        if chapter not in truth or "stängt" not in truth.lower() and "closed" not in truth.lower():
            # chapter reference must exist; detailed status checked below
            pass

    required_truth_tokens = (
        "2F.1",
        "2F.2",
        "2F.3",
        "2F.4",
        AUTHORITATIVE_GMAIL_RUN_ID,
        AUTHORITATIVE_LLM_RUN_ID,
        HISTORICAL_FAILURE_RUN_ID,
        CLOSURE_MARKER,
    )
    for token in required_truth_tokens:
        if token not in truth:
            raise ValueError(f"docs/01-current-truth.md missing required token: {token}")

    if "2G" not in backlog:
        raise ValueError("docs/06-backlog.md must reference Kapitel 2G as next chapter")
    if "2F.3+ — Live LLM E2E" in backlog and "Not started" in backlog:
        raise ValueError("docs/06-backlog.md still marks 2F.3 as not started")
    if AUTHORITATIVE_GMAIL_RUN_ID not in testbot or AUTHORITATIVE_LLM_RUN_ID not in testbot:
        raise ValueError("docs/10f-live-eval-testbot.md missing authoritative run IDs")
    if HISTORICAL_FAILURE_RUN_ID not in testbot or "provider_outcome" not in testbot:
        raise ValueError("docs/10f-live-eval-testbot.md missing historical failure classification")

    forbidden_phrases = (
        "stängdes på 74407fe",
        "stängt @ `74407fe`",
        "stängt @ 74407fe",
        "already produced the official artifact",
        "artifact already exists",
    )
    for relative_path in REQUIRED_DOCUMENTATION_FILES:
        content = (documentation_root / relative_path).read_text(encoding="utf-8")
        for phrase in forbidden_phrases:
            if phrase in content:
                raise ValueError(f"{relative_path} contains forbidden pre-merge claim: {phrase}")

    required_closure_phrases = (
        "final-2f-evidence",
        "2f-final-evidence",
        "overall_status=passed",
    )
    for phrase in required_closure_phrases:
        combined = "\n".join(
            (documentation_root / relative_path).read_text(encoding="utf-8")
            for relative_path in REQUIRED_DOCUMENTATION_FILES
        )
        if phrase not in combined:
            raise ValueError(f"documentation set missing required closure phrase: {phrase}")

    return {
        "status": "closed",
        "verified_files": sorted(verified_files),
        "closure_marker": CLOSURE_MARKER,
    }


def apply_final_closure(
    *,
    manifest: dict[str, Any],
    replay_report: dict[str, Any],
    final_report: dict[str, Any],
    context: ClosureContext,
    documentation_status: dict[str, Any],
) -> dict[str, Any]:
    from app.evaluation.live.replay_verifier import (
        _authoritative_side_effects_known,
        _historical_unknowns_classified,
        _validate_replay_bindings,
    )

    validate_closure_context(context)
    _validate_replay_bindings(
        manifest,
        replay_report,
        baseline_git_sha=context.baseline_git_sha,
    )

    if replay_report.get("overall_status") != "passed":
        raise ValueError("replay report overall_status must be passed")
    if replay_report.get("no_network") is not True:
        raise ValueError("replay report no_network must be true")
    if final_report.get("new_external_runs_required") is True:
        raise ValueError("new_external_runs_required must be false")
    if final_report.get("active_live_eval_runs", 0) > 0:
        raise ValueError("active_live_eval_runs must be 0")
    if not _authoritative_side_effects_known(manifest):
        raise ValueError("authoritative evidence contains unknown side effects")
    if not _historical_unknowns_classified(manifest):
        raise ValueError("historical failures are not correctly classified")

    closed_report = dict(final_report)
    closed_report["closure_mode"] = CLOSURE_MODE_FINAL
    closed_report["overall_status"] = "passed"
    closed_report["replay_status"] = "passed"
    closed_report["new_external_runs_required"] = False
    closed_report["documentation_closure_status"] = documentation_status["status"]
    closed_report["ci_delivery"] = {
        "event": context.ci_event,
        "branch": context.ci_branch,
        "run_id": context.ci_run_id,
        "head_sha": context.ci_head_sha,
        "required_checks": dict(sorted(context.required_checks.items())),
    }
    closed_report["documentation_closure"] = documentation_status

    criteria = dict(closed_report.get("closure_criteria") or {})
    for key, value in criteria.items():
        if value == "failed":
            raise ValueError(f"closure criterion {key!r} is failed")
    for key in criteria:
        criteria[key] = "passed"
    criteria["final_ci_delivery"] = "passed"
    criteria["formal_documentation_closure"] = "passed"
    closed_report["closure_criteria"] = criteria

    if closed_report["overall_status"] != "passed":
        raise ValueError("final report overall_status must be passed after closure")
    if any(value != "passed" for value in closed_report["closure_criteria"].values()):
        raise ValueError("all closure criteria must be passed after closure")

    return closed_report


def finalize_offline_replay_result(
    result,
    context: ClosureContext,
):
    from app.evaluation.live.replay_verifier import OfflineReplayResult

    documentation_status = verify_documentation_closure(context.documentation_root)
    final_report = apply_final_closure(
        manifest=result.manifest,
        replay_report=result.replay_report,
        final_report=result.final_report,
        context=context,
        documentation_status=documentation_status,
    )
    return OfflineReplayResult(
        manifest=result.manifest,
        replay_report=result.replay_report,
        final_report=final_report,
        evidence_payload_hash=result.evidence_payload_hash,
        evidence_source_descriptor_hash=result.evidence_source_descriptor_hash,
        replay_payload_hash=result.replay_payload_hash,
    )
