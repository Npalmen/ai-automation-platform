#!/usr/bin/env python3
"""Run alert/incident fixture setup or cleanup inside app container context."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.k12_browser_alert_incident_fixture import (  # noqa: E402
    cleanup_synthetic_alert_incidents,
    setup_synthetic_alert_incident,
)

tenant = sys.argv[2] if len(sys.argv) > 2 else "T_K12_BROWSER"
command = sys.argv[1] if len(sys.argv) > 1 else "setup"

if command == "cleanup":
    print(cleanup_synthetic_alert_incidents(tenant))
elif command == "setup":
    print(json.dumps(setup_synthetic_alert_incident(tenant)))
else:
    raise SystemExit(f"unknown command: {command}")
