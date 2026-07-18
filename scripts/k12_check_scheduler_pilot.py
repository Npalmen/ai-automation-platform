#!/usr/bin/env python3
"""Check scheduler paused via session — never prints credentials."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path("/opt/krowolf")
sys.path.insert(0, str(ROOT))

from scripts.k12_browser_common import load_browser_env, resolve_env_path

import requests

env = load_browser_env(resolve_env_path())
base = env.get("K12_BROWSER_BASE_URL", "https://api.krowolf.se").rstrip("/")
user = env.get("K12_BROWSER_USERNAME", "")
password = env.get("K12_BROWSER_PASSWORD", "")
if not user or not password:
    print("SCHEDULER_CHECK=SKIP missing_browser_credentials")
    sys.exit(0)

sess = requests.Session()
r = sess.post(
    f"{base}/auth/admin/login",
    json={"username": user, "password": password},
    headers={"Origin": base},
    timeout=20,
)
print(f"LOGIN_HTTP={r.status_code}")
me = sess.get(f"{base}/auth/admin/me", headers={"Origin": base}, timeout=20)
role = me.json().get("operator", {}).get("role") if me.status_code == 200 else None
print(f"SESSION_ROLE={role}")
st = sess.get(f"{base}/admin/system/status", headers={"Origin": base}, timeout=20)
print(f"SYSTEM_STATUS_HTTP={st.status_code}")
if st.status_code == 200:
    data = st.json()
    sched = data.get("runtime", {}).get("scheduler", {})
    mode = sched.get("run_mode") or sched.get("status") or sched.get("state")
    print(f"SCHEDULER_SIGNAL={json.dumps(mode)}")
else:
    print("SCHEDULER_SIGNAL=unavailable_for_read_only" if st.status_code == 403 else "SCHEDULER_SIGNAL=unknown")
