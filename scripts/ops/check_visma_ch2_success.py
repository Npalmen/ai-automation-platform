#!/usr/bin/env python3
import json, subprocess
code = r'''
import json
from app.repositories.postgres.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
try:
    row = db.execute(text("""
        SELECT status, last_error,
               payload->'result'->>'customer_created' AS customer_created,
               (payload->'result'->>'external_invoice_id') IS NOT NULL AS external_id_present,
               payload->'result'->>'customer_number' IS NOT NULL AS customer_number_present
        FROM integration_events
        WHERE integration_type='visma' AND status='success'
        ORDER BY id DESC LIMIT 1
    """)).fetchone()
    appr = db.execute(text("""
        SELECT request_payload->>'state' AS state
        FROM approval_requests
        WHERE tenant_id='T_NIKLAS_DEMO_001'
          AND approval_id LIKE 'finance_visma_export:%'
          AND job_id = (
            SELECT job_id FROM integration_events
            WHERE integration_type='visma' AND status='success'
            ORDER BY id DESC LIMIT 1
          )
        LIMIT 1
    """)).fetchone()
    print(json.dumps({
        "success_event": {
            "status": row[0] if row else None,
            "last_error": row[1] if row else None,
            "customer_created": row[2] if row else None,
            "external_id_present": bool(row[3]) if row else False,
            "customer_number_present": bool(row[4]) if row else False,
        },
        "approval_state": appr[0] if appr else None,
    }))
finally:
    db.close()
'''
proc=subprocess.run(["sudo","docker","exec","-w","/app","krowolf-app-1","python","-c",code],capture_output=True,text=True)
print(proc.stdout.strip() or proc.stderr[:400])
