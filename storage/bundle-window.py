#!/usr/bin/env python3
import re, subprocess

def extract(path_in_container, docker_cmd):
    raw = subprocess.check_output(docker_cmd, text=True)
    idx = raw.find("Ny kund")
    if idx < 0:
        return {"found": False}
    window = raw[max(0, idx-200): idx+120]
    return {
        "found": True,
        "window": window,
        "has_role_eq_admin": '==="admin"' in window or "==='admin'" in window,
        "has_role_eq_operations": '==="operations"' in window,
    }

old = extract(
    "old",
    ["docker", "run", "--rm", "krowolf-app:rc-967df7a181b7", "cat", "/app/frontend/dist/assets/index-CZD0W4zR.js"],
)
new = extract(
    "new",
    ["docker", "exec", "krowolf-app-1", "cat", "/app/frontend/dist/assets/index-DiSFbwfh.js"],
)

import json
print(json.dumps({"old": old, "new": new}, indent=2))
