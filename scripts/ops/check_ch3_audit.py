#!/usr/bin/env python3
import json, subprocess
code = r'''
import json
from app.repositories.postgres.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
try:
    rows = db.execute(text("""
        SELECT action, status, count(*) FROM audit_events
        WHERE tenant_id='T_NIKLAS_DEMO_001'
          AND action IN ('finance_visma_export','tenant_integrations_updated','visma_sandbox_test_job_created')
        GROUP BY action, status ORDER BY action, status
    """)).fetchall()
    rej = db.execute(text("""
        SELECT count(*) FROM approval_requests
        WHERE tenant_id='T_NIKLAS_DEMO_001'
          AND approval_id LIKE 'finance_visma_export:%'
          AND request_payload->>'state'='rejected'
          AND request_payload->>'resolution_note' LIKE '%ArticleId-fix%'
    """)).scalar()
    print(json.dumps({
        "audit_counts": [{"action": r[0], "status": r[1], "count": r[2]} for r in rows],
        "rejections_with_ch3_note": int(rej or 0),
    }))
finally:
    db.close()
'''
proc=subprocess.run(["sudo","docker","exec","-w","/app","krowolf-app-1","python","-c",code],capture_output=True,text=True)
print(proc.stdout.strip() or proc.stderr[:400])
