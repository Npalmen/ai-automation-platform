#!/usr/bin/env python3
"""Post-cleanup admin API verification — no secrets."""
import json
import os
import urllib.request
from pathlib import Path

ENV = Path("/opt/krowolf/.env.production")
admin_key = ""
for line in ENV.read_text().splitlines():
    if line.startswith("ADMIN_API_KEY="):
        admin_key = line.split("=", 1)[1].strip().strip('"')
        break

req = urllib.request.Request(
    "https://api.krowolf.se/admin/tenants",
    headers={"X-Admin-API-Key": admin_key, "Accept": "application/json"},
)
with urllib.request.urlopen(req, timeout=30) as resp:
    body = json.load(resp)

items = body.get("items") if isinstance(body, dict) else body
ids = [x.get("tenant_id") for x in items]
print(json.dumps({"http": resp.status, "tenant_count": len(ids), "tenant_ids": ids}, indent=2))

req2 = urllib.request.Request(
    "https://api.krowolf.se/admin/alerts/summary",
    headers={"X-Admin-API-Key": admin_key, "Accept": "application/json"},
)
with urllib.request.urlopen(req2, timeout=30) as resp2:
    alerts = json.load(resp2)
print(json.dumps({"alerts_summary": alerts}, indent=2))
