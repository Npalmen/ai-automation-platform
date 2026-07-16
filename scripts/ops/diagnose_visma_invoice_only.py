#!/usr/bin/env python3
"""Invoice-only validation hints using existing sandbox customer. Reports hints only."""
import json, subprocess
code = r'''
import json, requests
from app.repositories.postgres.database import SessionLocal
from app.integrations.visma.token_resolver import resolve_visma_access_token
from app.core.settings import get_settings
from app.finance.pre_accounting import build_visma_export_payload
from app.integrations.visma.adapter import VismaAdapter
from app.main import _resolve_visma_fiscal_year_id

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
invoice_body = dict(payload["invoice"])
db = SessionLocal()
out = {"attempts": []}
try:
    token = resolve_visma_access_token(db, "T_NIKLAS_DEMO_001", check_allowlist=False)
    base = get_settings().VISMA_API_URL.rstrip("/")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}
    adapter = VismaAdapter({"access_token": token, "api_url": base})
    fiscal = _resolve_visma_fiscal_year_id(adapter)
    if fiscal:
        invoice_body["FiscalYearId"] = fiscal
    cust_r = requests.get(
        f"{base}/customers?$filter=contains(Name,'Krowolf Sandbox')&$pagesize=1",
        headers=headers,
        timeout=30,
    )
    cust_r.raise_for_status()
    cust_items = cust_r.json()
    if isinstance(cust_items, dict):
        cust_items = cust_items.get("Data") or []
    if not cust_items:
        print(json.dumps({"error": "no_sandbox_customer"}))
        raise SystemExit(0)
    customer_id = cust_items[0].get("Id")
    invoice_body["CustomerId"] = customer_id
    invoice_body.pop("CustomerNumber", None)
    art_r = requests.get(f"{base}/articles?$pagesize=5", headers=headers, timeout=30)
    art_r.raise_for_status()
    arts = art_r.json()
    if isinstance(arts, dict):
        arts = arts.get("Data") or []
    article_id = arts[0].get("Id") if arts else None
    rows = list(invoice_body.get("Rows") or [])
    if rows and article_id:
        rows[0] = dict(rows[0])
        rows[0]["ArticleId"] = article_id
        invoice_body["Rows"] = rows
    for label, body in [
        ("invoice_without_article", dict(payload["invoice"]) | {"CustomerId": customer_id, "FiscalYearId": fiscal} if fiscal else {"CustomerId": customer_id}),
        ("invoice_with_article", invoice_body),
    ]:
        body = dict(body)
        body.pop("CustomerNumber", None)
        r = requests.post(f"{base}/customerinvoices", headers=headers, json=body, timeout=30)
        entry = {"label": label, "http": r.status_code}
        if not r.ok:
            try:
                err = r.json()
                msg = err.get("DeveloperErrorMessage") or err.get("Message")
                if isinstance(msg, str):
                    entry["hint"] = msg[:240]
            except Exception:
                entry["hint"] = "non_json"
        else:
            entry["created"] = True
        out["attempts"].append(entry)
    print(json.dumps(out))
finally:
    db.close()
'''
proc = subprocess.run(["sudo","docker","exec","-w","/app","krowolf-app-1","python","-c",code], capture_output=True, text=True)
print(proc.stdout.strip() or proc.stderr[:500])
