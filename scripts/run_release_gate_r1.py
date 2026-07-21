"""Run the consolidated R1 release gate test suites.

This script is intended to be run at the end of a sprint/release candidate.
It executes one regression phase and one E2E phase in sequence, so teams avoid
running many repeated full-suite runs during feature implementation.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass

from app.evaluation.live.constants import PYTEST_MARKER_EXPR


@dataclass(frozen=True)
class GatePhase:
    name: str
    description: str
    tests: tuple[str, ...]


REGRESSION_PHASE = GatePhase(
    name="regression",
    description="Cross-slice regression checks for R1-critical modules.",
    tests=(
        "tests/test_setup_wizard.py",
        "tests/test_onboarding.py",
        "tests/test_integration_health.py",
        "tests/test_cases.py",
        "tests/test_control_panel.py",
        "tests/test_customer_saas_surfaces.py",
        "tests/test_production_hardening.py",
        "tests/test_production_readiness.py",
        "tests/test_dispatch_policy.py",
        "tests/test_dispatch_approval.py",
        "tests/test_auto_dispatch.py",
        # Security and isolation gates (added in go-live validation)
        "tests/test_tenant_isolation_http.py",
        "tests/test_auth.py",
        "tests/test_admin_operations_triage.py",
    ),
)

E2E_PHASE = GatePhase(
    name="e2e",
    description="Pilot flow E2E matrix: inbox -> classification -> approval -> dispatch.",
    tests=(
        "tests/test_gmail_process_inbox.py",
        "tests/test_mvp_flow.py",
        "tests/test_email_approval.py",
        "tests/test_dispatch_engine.py",
        "tests/test_dispatch_time_range.py",
    ),
)

ALL_PHASES = (REGRESSION_PHASE, E2E_PHASE)


def _run_phase(phase: GatePhase, *, verbose: bool) -> int:
    print(f"\n=== R1 Release Gate: {phase.name.upper()} ===")
    print(phase.description)
    for test_file in phase.tests:
        print(f"  - {test_file}")

    cmd = [sys.executable, "-m", "pytest", "-m", PYTEST_MARKER_EXPR, *phase.tests]
    if verbose:
        print(f"Running command: {' '.join(cmd)}")

    completed = subprocess.run(cmd, check=False)
    if completed.returncode != 0:
        print(f"Phase '{phase.name}' failed with exit code {completed.returncode}.")
    else:
        print(f"Phase '{phase.name}' passed.")
    return completed.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run consolidated R1 release gate test phases."
    )
    parser.add_argument(
        "--phase",
        choices=("all", "regression", "e2e"),
        default="all",
        help="Run all phases or a single phase.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print command details.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected_phases = ALL_PHASES
    if args.phase != "all":
        selected_phases = tuple(p for p in ALL_PHASES if p.name == args.phase)

    for phase in selected_phases:
        phase_exit_code = _run_phase(phase, verbose=args.verbose)
        if phase_exit_code != 0:
            return phase_exit_code

    print("\nR1 release gate passed (all requested phases).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
