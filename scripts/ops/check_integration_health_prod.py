#!/usr/bin/env python3
import json, urllib.request
key = open("/opt/krowolf/storage/tenant_keys/T_NIKLAS_DEMO_001.api_key").read().strip()
req = urllib.request.Request(
    "https://api.krowolf.se/integrations/health",
    headers={"X-API-Key": key},
)
with urllib.request.urlopen(req, timeout=30) as resp:
    d = json.load(resp)
print(json.dumps({
    "http": resp.status,
    "overall_status": d.get("overall_status"),
    "systems": {
        k: {"status": (v or {}).get("status")}
        for k, v in (d.get("systems") or {}).items()
        if k in ("gmail", "monday", "fortnox", "visma", "google_sheets")
    },
}))
