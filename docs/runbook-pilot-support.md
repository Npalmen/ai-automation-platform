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
# PostgreSQL backup (lokal dev)
pg_dump ai_platform > backup_$(date +%Y%m%d).sql

# Restore
psql ai_platform < backup_20260510.sql
```

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

## Eskalering

| Situation | Kontakta |
|-----------|----------|
| API ner | Plattformsteam (omedelbart) |
| OAuth-token revokad | Plattformsteam (inom 1h) |
| Felaktigt kundmail skickat | Plattformsteam + pilot-kund (omedelbart) |
| Databasproblem | Plattformsteam (omedelbart) |
| Felklassificering | Rapportera via ärendedetaljer → "Manuell granskning" |
