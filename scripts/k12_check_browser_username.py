#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, "/opt/krowolf")
from scripts.k12_browser_common import load_browser_env, resolve_env_path
e = load_browser_env(resolve_env_path())
print("BROWSER_USERNAME=" + e.get("K12_BROWSER_USERNAME", ""))
print("USERNAME_MATCH_ADMIN=" + str(e.get("K12_BROWSER_USERNAME", "") == "admin"))
print("PASSWORD_SET=" + str(bool(e.get("K12_BROWSER_PASSWORD", ""))))
