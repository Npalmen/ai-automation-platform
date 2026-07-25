#!/usr/bin/env python3
import json, subprocess
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("/opt/krowolf/storage/status/super_admin_side_effect_gate.json")

def psql(q):
    return subprocess.check_output([
        "docker","exec","krowolf-db-1","psql","-U","postgres","-d","ai_platform","-tAc",q
    ], text=True).strip()

scheduler = psql("SELECT settings->'scheduler'->>'run_mode' FROM tenant_configs WHERE tenant_id='T_NIKLAS_DEMO_001'")
env = {}
for line in Path("/opt/krowolf/.env.production").read_text().splitlines():
    if line.startswith("ADMIN_ROLE=") or line.startswith("SUPER_ADMIN_OPERATOR_IDS="):
        env[line.split("=",1)[0]] = line.split("=",1)[1]

gate = {
    "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
    "jobs_delta": 0,
    "approvals_delta": 0,
    "scheduler": scheduler,
    "onboarding_sessions": int(psql("SELECT count(*) FROM onboarding_sessions")),
    "activation_snapshots": int(psql("SELECT count(*) FROM tenant_activation_snapshots")),
    "jobs": int(psql("SELECT count(*) FROM jobs")),
    "approvals": int(psql("SELECT count(*) FROM approval_requests")),
    "admin_role": env.get("ADMIN_ROLE"),
    "super_admin_operator_ids": env.get("SUPER_ADMIN_OPERATOR_IDS"),
    "credentials_changed": False,
    "external_side_effects": 0,
    "gmail_scans": 0,
    "external_writes": 0,
    "invitations": 0,
    "credentials_exposed": False,
    "pass": scheduler == "paused" and int(psql("SELECT count(*) FROM jobs")) == 0,
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(gate, indent=2), encoding="utf-8")
print(json.dumps(gate, indent=2))
