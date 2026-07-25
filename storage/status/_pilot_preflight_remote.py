#!/usr/bin/env python3
import json
from app.repositories.postgres.database import SessionLocal
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
from sqlalchemy import text

db = SessionLocal()
settings = TenantConfigRepository.get_settings(db, "T_NIKLAS_DEMO_001")
auto = settings.get("auto_actions") or {}
automation = settings.get("automation") or {}
scheduler = settings.get("scheduler") or {}
internal = settings.get("internal_pilot") or {}
try:
    active_eval = db.execute(
        text("SELECT count(*) FROM evaluation_runs WHERE status IN ('running', 'claimed')")
    ).scalar()
except Exception:
    active_eval = 0
print(
    json.dumps(
        {
            "tenant_id": "T_NIKLAS_DEMO_001",
            "scheduler_run_mode": scheduler.get("run_mode"),
            "demo_mode": automation.get("demo_mode"),
            "automatic_gmail_replies": automation.get("automatic_gmail_replies"),
            "auto_actions": auto,
            "internal_pilot": internal,
            "active_live_eval_runs": int(active_eval or 0),
        },
        indent=2,
    )
)
db.close()
