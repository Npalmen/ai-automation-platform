# Google Cloud OAuth — Gmail (Pilot)

> **Manuell konfiguration i Google Cloud Console.** Krowolf ändrar inget i GCP automatiskt.

## OAuth client

| Setting | Value |
|---------|--------|
| Client type | **Web application** |
| Application name | Krowolf Platform (production) |
| Authorized redirect URI (canonical) | `https://api.krowolf.se/integrations/google_mail/oauth/callback` |

**Ingen wildcard redirect URI.** Lägg endast till exakt produktions-URI ovan (plus `http://localhost:8000/integrations/google_mail/oauth/callback` för lokal utveckling om behövs).

## Platform environment (`.env.production`)

Root-skyddad fil (`chmod 600`, ägs av deploy-användare):

```
GOOGLE_OAUTH_CLIENT_ID=<from GCP>
GOOGLE_OAUTH_CLIENT_SECRET=<from GCP>
GOOGLE_OAUTH_REDIRECT_URI=https://api.krowolf.se/integrations/google_mail/oauth/callback
GOOGLE_OAUTH_SCOPES=https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.modify
```

Legacy (kan tas bort efter tenant-OAuth):

```
GOOGLE_MAIL_ACCESS_TOKEN=
GOOGLE_OAUTH_REFRESH_TOKEN=
GOOGLE_MAIL_USER_ID=
```

## Scope contract — intern pilot (read-only + handoff)

| Scope | Pilot | Syfte |
|-------|-------|--------|
| `gmail.readonly` | **Ja** | Label-scoped inbox scan |
| `gmail.modify` | **Ja** | Manual-review handoff (labels, UNREAD) — används av `apply_manual_review_label` |
| `gmail.send` | **Nej** | Kräver **ny consent** när send-flödet är tenant-DB-wirat och godkänt |

**gmail.send** läggs till senare genom ny OAuth-consent när:

1. `action_executor.py` skickar `db` till `get_integration_connection_config` för alla send-paths
2. Pilot godkänner Gmail-send som produktfunktion
3. `GOOGLE_OAUTH_SCOPES` utökas med `https://www.googleapis.com/auth/gmail.send` i prod-env och GCP consent screen

## Publishing status

| Phase | Krav |
|-------|------|
| **Testing (default)** | OAuth consent screen i *Testing*; lägg till **Test users** (t.ex. `niklas.palm@sol-f.se`) |
| **In production** | App verification hos Google om *sensitive/restricted* scopes används; publicera consent screen |

`gmail.modify` räknas som **sensitive**. För intern pilot räcker **Testing + test users**. För externa kunder krävs verifiering och *In production*.

## Operator flow (efter deploy)

1. `/ops/customers/T_NIKLAS_DEMO_001` → **Anslut Google**
2. Google consent → callback → tenant credential i `oauth_credentials` (`provider=google_mail`)
3. Verifiera: `GET /admin/tenants/T_NIKLAS_DEMO_001/integrations/google_mail/status` → `connection_state=connected`
4. Read-only: `POST /integrations/google_mail/test-read` (tenant API key)
5. Label-scoped scan (ingen scheduler): `POST /gmail/process-inbox` med `dry_run=true`

## Säkerhet

- OAuth **state** är opaque, HMAC-signerad, 15 min TTL, single-use
- Callback binder tenant från state — inte från browser query utan verifiering
- Refresh tokens lagras endast i DB; exponeras aldrig i API/UI
- Client secret endast i server-env

## Live status (2026-07-20)

| Check | Status |
|-------|--------|
| Tenant `T_NIKLAS_DEMO_001` connected | PASS |
| `credential_source` | `tenant_oauth` |
| Test-read | PASS |
| Krowolf scopes used | `readonly` + `modify` only |
| Stored grant scope superset | May include `gmail.send`, `spreadsheets` — **not invoked** |
| Gmail send | **Disabled** |
| Scheduler | **Paused** |

## Checklista före intern live

- [ ] Redirect URI matchar exakt i GCP och `GOOGLE_OAUTH_REDIRECT_URI`
- [ ] Test user tillagd i GCP om app är i Testing
- [ ] Consent scopes = readonly + modify (inte send)
- [ ] `GOOGLE_OAUTH_*` satt i produktion utan att committas
- [x] Tenant ansluten via UI (inte Playground)
- [x] `test-read` PASS
- [x] Scheduler fortfarande **paused**
- [ ] Dry-run/live scan under soak — se `docs/niklas-gmail-soak-log.md`
