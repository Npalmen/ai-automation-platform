#!/usr/bin/env python3
import sys
from pathlib import Path
ROOT = Path("/opt/krowolf")
sys.path.insert(0, str(ROOT))
from scripts.k12_browser_common import load_browser_env, resolve_env_path
import requests

env = load_browser_env(resolve_env_path())
base = env["K12_BROWSER_BASE_URL"].rstrip("/")
user = env["K12_BROWSER_USERNAME"]
password = env["K12_BROWSER_PASSWORD"]
r = requests.post(
    f"{base}/auth/admin/login",
    json={"username": user, "password": password},
    headers={"Content-Type": "application/json"},
    timeout=20,
)
print(f"NO_ORIGIN HTTP={r.status_code}")
if r.status_code == 200:
    me = requests.Session()
    me.cookies.update(r.cookies)
    m = me.get(f"{base}/auth/admin/me", timeout=20)
    print(f"ME_HTTP={m.status_code} ROLE={m.json().get('operator',{}).get('role') if m.status_code==200 else None}")
