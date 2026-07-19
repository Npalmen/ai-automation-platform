#!/usr/bin/env python3
"""Run approval fixture setup inside app container context."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.k12_browser_approval_fixture import setup_synthetic_approval

tenant = sys.argv[1] if len(sys.argv) > 1 else "T_K12_BROWSER"
print(json.dumps(setup_synthetic_approval(tenant)))
