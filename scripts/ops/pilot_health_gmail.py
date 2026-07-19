#!/usr/bin/env python3
import json
import urllib.request
from pathlib import Path

k = Path("/app/storage/tenant_keys/T_NIKLAS_DEMO_001.api_key").read_text().strip()
req = urllib.request.Request(
    "https://api.krowolf.se/integrations/health",
    headers={"X-API-Key": k, "Accept": "application/json"},
)
with urllib.request.urlopen(req, timeout=60) as resp:
    body = json.load(resp)
gmail = (body.get("systems") or {}).get("gmail") or {}
print(json.dumps({
    "http": resp.status,
    "gmail_status": gmail.get("status"),
    "gmail_message": gmail.get("message"),
    "gmail_recommended_action": gmail.get("recommended_action"),
    "gmail_checks": gmail.get("checks"),
    "gmail_last_error_message": (gmail.get("last_error_message") or "")[:120] or None,
}, indent=2))
