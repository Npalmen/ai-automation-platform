#!/usr/bin/env python3
"""Read-only sandbox invoice verification — safe metadata only."""
import json, subprocess
code = r'''
import json, requests
from app.repositories.postgres.database import SessionLocal
from app.integrations.visma.token_resolver import resolve_visma_access_token
from app.core.settings import get_settings

db = SessionLocal()
try:
    token = resolve_visma_access_token(db, "T_NIKLAS_DEMO_001", check_allowlist=False)
    base = get_settings().VISMA_API_URL.rstrip("/")
    h = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    out = {"invoices": [], "customers_sandbox_count": 0}
    cr = requests.get(f"{base}/customers?$filter=contains(Name,'Krowolf Sandbox')&$pagesize=10", headers=h, timeout=30)
    if cr.ok:
        items = cr.json()
        if isinstance(items, dict):
            items = items.get("Data") or []
        out["customers_sandbox_count"] = len(items)
    ir = requests.get(f"{base}/customerinvoices?$filter=contains(CustomerName,'Krowolf')&$pagesize=10", headers=h, timeout=30)
    ir.raise_for_status()
    invs = ir.json()
    if isinstance(invs, dict):
        invs = invs.get("Data") or []
    for inv in invs:
        if not isinstance(inv, dict):
            continue
        name = str(inv.get("CustomerName") or "")
        ref = str(inv.get("YourReference") or inv.get("YourOrderReference") or "")
        blob = (name + " " + ref).lower()
        if "krowolf" not in blob and "sandbox" not in blob:
            continue
        out["invoices"].append({
            "synthetic_customer": "sandbox" in name.lower() or "krowolf" in name.lower(),
            "has_reference_marker": "sandbox" in ref.lower() or "ch2" in ref.lower(),
            "currency": inv.get("CurrencyCode"),
            "total": inv.get("TotalAmount") or inv.get("Total"),
            "state_hint": inv.get("Status") or inv.get("InvoiceState"),
            "sent": bool(inv.get("Sent") or inv.get("IsSent")),
        })
    out["sandbox_invoice_count"] = len(out["invoices"])
    print(json.dumps(out))
finally:
    db.close()
'''
proc = subprocess.run(["sudo","docker","exec","-w","/app","krowolf-app-1","python","-c",code], capture_output=True, text=True)
print(proc.stdout.strip() or proc.stderr[:500])
