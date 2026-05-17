# Runbook: Pilot Support Playbook

## Syfte
Denna runbook täcker hur pilot-support hanteras: vad AI gör vs vad operatören gör, vanliga frågor, eskaleringsvägar och datahantering.

## Vad AI Gör (Automatiskt)

| Funktion | Automatisk? | Kräver godkännande? |
|----------|-------------|---------------------|
| Läsa inkommande mail | Ja | Nej |
| Klassificera lead/support/faktura | Ja | Nej |
| Extrahera kunddata | Ja | Nej |
| Bedöma lead-score och prioritet | Ja | Nej |
| Skapa utkast på kundsvar | Ja | Ja (approval-gated) |
| Skicka mail till kund | Nej | Ja — operatören godkänner |
| Skapa Monday-item | Nej | Ja — operatören godkänner |
| Exportera till Fortnox | Nej | Ja — operatören godkänner |
| SLA-påminnelser (interna) | Ja | Nej |
| Daglig sammanfattning | Ja | Nej |

## Daglig Rutin (Operatör)

### Morgon (~5-10 min)
1. Öppna Operationscockpit → kolla "Kräver åtgärd" och "Riskerar SLA"
2. Gå igenom väntande godkännanden (mail, dispatch)
3. Kontrollera SLA-riskerna — svara på leads som väntat > 24h

### Under dagen
- När AI föreslår svar: granska → godkänn eller redigera
- Uppdatera arbetsorderstatus när tekniker rapporterar (Starta / Klart / Blockerad)
- Lägg till material och tid i operationsworkspace

### Avslut / Fakturering
1. Kontrollera att underlag-status är "Redo"
2. Öppna ärende → "Sammanställ projekt" → granska
3. Klicka "Förhandsvisa i Fortnox" → kontrollera att data stämmer
4. Godkänn Fortnox-export

## Vanliga Frågor (Pilot-kund)

### "Vad händer med mina mail?"
AI läser inkommande mail, analyserar dem och förbereder svar. Ingen mail skickas utan att operatören godkänner. Du kan se alla AI-svar i godkännaelistan.

### "Kan AI skicka fel svar till kund?"
Nej. All kundkommunikation är approval-gated. AI föreslår, operatören beslutar och skickar.

### "Varför klassificerades detta mail fel?"
Felklassificeringar kan hanteras via "Manuell granskning" i ärendepanelen. Rapportera till plattformsteam för att förbättra klassificering.

### "Hur vet jag om ett lead tappats?"
Cockpit-vy visar "Riskerar SLA" — dessa leads behöver omedelbart svar. Daglig digest inkluderar också öppna leads.

### "Kan jag använda Fortnox som vanligt?"
Ja. Plattformen läser data från Fortnox och skickar tillbaka förslag — men ändrar ingenting i Fortnox utan explicit godkännande.

## Troubleshooting

### Inget mail läses in
1. Kontrollera Gmail-integration: `GET /dashboard/integration-health`
2. Om `gmail.status = error`: se [runbook-oauth.md](runbook-oauth.md)
3. Kontrollera att scheduler körs: `GET /dashboard/control`

### AI-svar saknas i godkännaelistan
1. Kontrollera att `auto_actions.leads_enabled = true` i kontrollpanelen
2. Se jobblogg för felmeddelanden
3. Om jobbet har `status = failed`: kontrollera `/cases/{job_id}` → Fel-sektionen

### Monday-item skapas inte
1. Kontrollera Monday-integration: `GET /dashboard/integration-health`
2. Kontrollera routing: `GET /tenant/memory` → routing_hints
3. Om board saknas: kör Monday-scanner via Setup-vyn

### Fortnox-export misslyckas
1. Kontrollera Fortnox API-token
2. Kontrollera att kund finns i Fortnox (eller skapa ny)
3. Se `GET /cases/{job_id}/finance/export-status` för detaljer

## Datahantering

### Vad lagras?
- Inkommande mail (metadata + body) i PostgreSQL
- AI-analys och klassificering
- Kundkommunikation (trådar)
- Arbetsorder och projektdata
- Godkänna-historik (vem godkände vad och när)

### Backup

```bash
# Daglig backup (produktionsmiljö — kör som cron kl 02:00)
pg_dump "$DATABASE_URL" | gzip > /backups/ai_platform_$(date +%Y%m%d_%H%M).sql.gz

# Manuell backup inför driftsättning
pg_dump "$DATABASE_URL" > /backups/pre_deploy_$(date +%Y%m%d_%H%M).sql

# Restore (stoppa applikationen först)
gunzip -c /backups/ai_platform_20260510_0200.sql.gz | psql "$DATABASE_URL"
python scripts/create_tables.py   # idempotent — säkert att köra efter restore
python scripts/smoke_check.py --base-url https://api.krowolf.se --expect-production
```

**Rekommenderad backup-frekvens:** Dagligen automatiskt + manuellt inför varje driftsättning.
**Retention:** 14 dagars rullande backup — äldre backuper tas bort automatiskt (eller manuellt).
**Rehearsal:** Testa restore i en isolerad miljö en gång i månaden. Dokumentera datum och resultat.

Se fullständig backup/restore-procedur i `docs/12-production-guide.md#backup-and-restore`.

### Dataretention
- Jobb-records bevaras indefinit i MVP (retention policy planeras för v2)
- Tenant-konfiguration och nycklar roteras manuellt vid behov

## API-nyckel Rotation

```bash
# Rotera API-nyckel för en tenant (kräver admin-nyckel)
POST /admin/tenants/{tenant_id}/rotate-key
Header: X-Admin-API-Key: <ADMIN_API_KEY>

# Spara den nya nyckeln omedelbart — visas bara en gång
```

## Onboarding Ny Pilot-kund (Checklista)

- [ ] Skapa tenant via `/admin/tenants`
- [ ] Konfigurera Gmail OAuth
- [ ] Konfigurera Monday (om relevant) — kör scanner
- [ ] Konfigurera Fortnox API-token — kör scanner
- [ ] Sätt routing_hints i tenant memory
- [ ] Aktivera relevant automation (leads / support / invoices)
- [ ] Kör pilot readiness check: `GET /dashboard/pilot-readiness`
- [ ] Verifiera att inbox-sync fungerar (skicka testmail)
- [ ] Informera kunden om vad AI gör / inte gör

## Misslyckade jobb — triage

Misslyckade jobb och dispatchar visas i Super Admin "Behöver hjälp"-kön (`GET /admin/operations/needs-help`).

### Steg 1 — Identifiera

Öppna Super Admin → ladda om åtgärdskön. Välj en rad med `severity: high` eller `critical`.

### Steg 2 — Diagnostisera

| Felmeddelande | Trolig orsak | Åtgärd |
|---------------|--------------|--------|
| `invalid_grant` / OAuth-fel | Gmail-token utgånget | Se `docs/runbook-oauth.md` |
| `401 Unauthorized` (Monday) | API-nyckel ogiltig | Uppdatera `MONDAY_API_KEY`, starta om |
| `401 Unauthorized` (Fortnox) | Access-token utgånget | Uppdatera `FORTNOX_ACCESS_TOKEN`, starta om |
| `No matching board` | Monday-scanner ej körd | Kör Monday-scanner i Setup |
| `Customer not found in Fortnox` | Kund saknas i Fortnox | Skapa kund i Fortnox, försök igen |
| `LLM quota exceeded` | OpenAI-ratelimit | Vänta och kör om jobbet |
| `DB connection error` | Databas nåbar ej | Kontrollera `DATABASE_URL` och uppkoppling |

### Steg 3 — Åtgärda

- **Kör om jobbet:** Klicka "Öppna ärende" → i ärendevyn, byt status till `pending` och kör om via `POST /jobs/{job_id}/auto-dispatch`.
- **Avsluta jobbet:** Byt status till `failed` i statusväljaren. Logga incidenten.
- **Misslyckad dispatch (3 försök / dead):** Skicka manuellt via ärendedetaljen eller skapa en manuell åtgärd.

### Steg 4 — Kontrollera

Ladda om åtgärdskön och bekräfta att raden är borta. Kontrollera integrationshälsa.

---

## Eskalering

| Situation | Kontakta |
|-----------|----------|
| API ner | Plattformsteam (omedelbart) |
| OAuth-token revokad | Plattformsteam (inom 1h) |
| Felaktigt kundmail skickat | Plattformsteam + pilot-kund (omedelbart) |
| Databasproblem | Plattformsteam (omedelbart) |
| Felklassificering | Rapportera via ärendedetaljer → "Manuell granskning" |
