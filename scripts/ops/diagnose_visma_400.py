#!/usr/bin/env python3
"""Safe Visma validation hints — reports HTTP status + short DeveloperErrorMessage only."""
import json, subprocess
code = r'''
import json, requests
from datetime import date
from app.repositories.postgres.database import SessionLocal
from app.integrations.visma.token_resolver import resolve_visma_access_token
from app.core.settings import get_settings
from app.finance.pre_accounting import build_visma_export_payload
from app.integrations.visma.adapter import VismaAdapter
from app.main import _resolve_visma_terms_of_payment_id, _resolve_visma_fiscal_year_id

draft = {
    "tenant_id": "T_NIKLAS_DEMO_001",
    "job_id": "sandbox-diagnose",
    "supplier_name": "Krowolf Sandbox Kund",
    "supplier_email": "sandbox-verifiering@test.krowolf.internal",
    "amount_ex_vat": 100.0,
    "vat_rate": 25,
    "due_date": "2026-08-31",
    "invoice_number": "SANDBOX-VISMA-DIAG",
    "expense_category": "services",
}
payload = build_visma_export_payload(draft)
customer_body = dict(payload["customer"])
invoice_body = dict(payload["invoice"])
db = SessionLocal()
out = {"validation_posts": [], "resolvers": {}}
try:
    token = resolve_visma_access_token(db, "T_NIKLAS_DEMO_001", check_allowlist=False)
    base = get_settings().VISMA_API_URL.rstrip("/")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}
    adapter = VismaAdapter({"access_token": token, "api_url": base})
    terms = _resolve_visma_terms_of_payment_id(adapter)
    fiscal = _resolve_visma_fiscal_year_id(adapter)
    out["resolvers"] = {"terms": bool(terms), "fiscal_year": bool(fiscal)}
    if terms:
        customer_body["TermsOfPaymentId"] = terms
    if fiscal:
        invoice_body["FiscalYearId"] = fiscal
    # Invoice still needs CustomerId — use zero GUID placeholder to surface row-level errors only.
    invoice_body["CustomerId"] = "00000000-0000-0000-0000-000000000001"
    invoice_body.pop("CustomerNumber", None)
    for step, path, body in [
        ("validate_customer", "customers", customer_body),
        ("validate_invoice", "customerinvoices", invoice_body),
    ]:
        r = requests.post(f"{base}/{path}", headers=headers, json=body, timeout=30)
        entry = {"step": step, "http": r.status_code}
        if not r.ok:
            try:
                err = r.json()
                entry["error_code"] = err.get("ErrorCode") or err.get("Code")
                msg = err.get("DeveloperErrorMessage") or err.get("Message")
                if isinstance(msg, str):
                    entry["hint"] = msg[:240]
            except Exception:
                entry["hint"] = "non_json_error"
        else:
            entry["unexpected_success"] = True
        out["validation_posts"].append(entry)
    print(json.dumps(out))
finally:
    db.close()
'''
proc = subprocess.run(["sudo","docker","exec","-w","/app","krowolf-app-1","python","-c",code], capture_output=True, text=True)
print(proc.stdout.strip() or proc.stderr[:500])
