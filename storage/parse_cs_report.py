#!/usr/bin/env python3
import json, re
from pathlib import Path
report = Path("/opt/krowolf/storage/status/customer_settings_pilot_role_report.json")
text = report.read_text(encoding="utf-8")
data = json.loads(text)
print("overall_status", data.get("overall_status"))
print("restore_status", data.get("restore_status"))
print("runtime_code_sha", data.get("runtime_code_sha"))
print("release_id", data.get("release_id"))
print("credentials_exposed", data.get("credentials_exposed"))
print("external_side_effects", data.get("external_side_effects"))
print("mutations", json.dumps(data.get("mutations"), indent=2))
print("side_effect", json.dumps(data.get("side_effect_delta"), indent=2)[:1500])
for role, payload in (data.get("roles") or {}).items():
    fails = [c for c in payload.get("checks", []) if c.get("status") == "FAIL"]
    print(f"ROLE {role} status={payload.get('status')} fails={len(fails)}")
    for f in fails:
        print(" ", f.get("name"), f.get("detail", ""))
patterns = [r'access_token', r'refresh_token', r'password', r'Bearer ']
print("secret_scan", any(re.search(p, text, re.I) for p in patterns))
