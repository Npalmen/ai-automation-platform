#!/usr/bin/env python3
import json, subprocess
code = r'''
import json
from app.repositories.postgres.database import SessionLocal
from app.main import _get_visma_adapter_for_tenant, _resolve_visma_terms_of_payment_id, _resolve_visma_fiscal_year_id
from app.finance.pre_accounting import build_visma_export_payload

db = SessionLocal()
try:
    adapter = _get_visma_adapter_for_tenant(db, "T_NIKLAS_DEMO_001")
    draft = {
        "tenant_id": "T_NIKLAS_DEMO_001",
        "job_id": "check",
        "supplier_name": "Krowolf Sandbox Kund",
        "supplier_email": "sandbox-verifiering@test.krowolf.internal",
        "amount_ex_vat": 100.0,
        "vat_rate": 25,
        "due_date": "2026-08-31",
        "invoice_number": "SANDBOX",
        "expense_category": "services",
    }
    payload = build_visma_export_payload(draft)
    customer = dict(payload["customer"])
    tid = _resolve_visma_terms_of_payment_id(adapter)
    if tid:
        customer["TermsOfPaymentId"] = tid
    print(json.dumps({
        "terms_resolved": bool(tid),
        "fiscal_year_resolved": bool(_resolve_visma_fiscal_year_id(adapter)),
        "customer_field_count": len(customer),
        "customer_has_terms": "TermsOfPaymentId" in customer,
        "invoice_row_count": len((payload.get("invoice") or {}).get("Rows") or []),
    }))
finally:
    db.close()
'''
proc=subprocess.run(["sudo","docker","exec","-w","/app","krowolf-app-1","python","-c",code],capture_output=True,text=True)
print(proc.stdout.strip() or proc.stderr[:500])
