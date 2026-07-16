#!/usr/bin/env python3
"""Read-only Visma invoice row + article shape probe. No writes."""
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
    out = {}
    for label, path in [
        ("articles", "articles?$pagesize=3"),
        ("customers_sandbox", "customers?$filter=contains(Name,'Krowolf Sandbox')&$pagesize=3"),
        ("invoices", "customerinvoices?$pagesize=1"),
    ]:
        r = requests.get(f"{base}/{path}", headers=h, timeout=30)
        out[label] = {"http": r.status_code, "count": 0, "row_keys": [], "article_has_id": False}
        if not r.ok:
            continue
        data = r.json()
        items = data if isinstance(data, list) else (data.get("Data") or data.get("data") or [])
        out[label]["count"] = len(items)
        if label == "articles" and items:
            out[label]["article_has_id"] = bool(items[0].get("Id"))
            out[label]["keys"] = sorted(items[0].keys())[:12]
        if label == "invoices" and items:
            inv_id = items[0].get("Id")
            out[label]["has_invoice"] = bool(inv_id)
            if inv_id:
                rr = requests.get(f"{base}/customerinvoices/{inv_id}/rows?$pagesize=1", headers=h, timeout=30)
                out[label]["rows_http"] = rr.status_code
                if rr.ok:
                    rows = rr.json()
                    row_items = rows if isinstance(rows, list) else (rows.get("Data") or [])
                    if row_items:
                        out[label]["row_keys"] = sorted(row_items[0].keys())[:18]
    print(json.dumps(out))
finally:
    db.close()
'''
proc = subprocess.run(["sudo","docker","exec","-w","/app","krowolf-app-1","python","-c",code], capture_output=True, text=True)
print(proc.stdout.strip() or proc.stderr[:500])
