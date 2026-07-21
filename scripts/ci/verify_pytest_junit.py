#!/usr/bin/env python3
"""Validate pytest JUnit XML output for strict CI gates."""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET


def _aggregate(root: ET.Element) -> dict[str, int]:
    if root.tag == "testsuites":
        totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
        for suite in root.findall("testsuite"):
            totals["tests"] += int(suite.get("tests", 0))
            totals["failures"] += int(suite.get("failures", 0))
            totals["errors"] += int(suite.get("errors", 0))
            totals["skipped"] += int(suite.get("skipped", 0))
        return totals

    return {
        "tests": int(root.get("tests", 0)),
        "failures": int(root.get("failures", 0)),
        "errors": int(root.get("errors", 0)),
        "skipped": int(root.get("skipped", 0)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("junit_path")
    parser.add_argument("--expected", type=int, required=True)
    parser.add_argument(
        "--require-zero-skipped",
        action="store_true",
        default=True,
    )
    args = parser.parse_args()

    root = ET.parse(args.junit_path).getroot()
    totals = _aggregate(root)

    problems: list[str] = []
    if totals["tests"] != args.expected:
        problems.append(
            f"expected {args.expected} tests, junit reports {totals['tests']}"
        )
    if totals["failures"] != 0:
        problems.append(f"failures={totals['failures']}")
    if totals["errors"] != 0:
        problems.append(f"errors={totals['errors']}")
    if args.require_zero_skipped and totals["skipped"] != 0:
        problems.append(f"skipped={totals['skipped']}")

    if problems:
        print(
            "JUnit gate failed:",
            "; ".join(problems),
            f"(totals={totals})",
            file=sys.stderr,
        )
        return 1

    print(
        f"JUnit gate passed: tests={totals['tests']} "
        f"failures=0 errors=0 skipped=0"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
