#!/usr/bin/env python3
import json
p = "/opt/krowolf/storage/status/k12_browser_read_only_report.json"
try:
    d = json.load(open(p))
except FileNotFoundError:
    print("REPORT=missing")
    raise SystemExit(1)
print("STATUS=" + str(d.get("status")))
print("ROLE_EXPECTED=" + str(d.get("role_expected")))
print("ROLE_RETURNED=" + str(d.get("role_returned")))
for c in d.get("checks", []):
    print(f"CHECK {c.get('name')} {c.get('status')} {c.get('detail','')}")
