# Runbook: Scheduler & Cron

## Syfte
Denna runbook beskriver hur plattformens schemalagda jobb startas, kontrolleras och återstartas i en pilot- eller produktionsmiljö.

## Bakgrund

Plattformen har en inbyggd scheduler som körs i samma process som FastAPI-appen (via `asyncio` bakgrundstask). Den ansvarar för:

- **Inbox sync**: Läser in nya mail från Gmail och skapar jobb
- **Daily digest**: Skickar daglig sammanfattning till operatör
- **SLA reminders**: Identifierar leads som missas SLA-gränsen och skapar interna påminnelser

## Starta Scheduler

Schedulern startas automatiskt när appen startar. Se `app/main.py` → `_run_scheduler_pass()`.

```bash
# Starta appen (lokalt)
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Kontrollera att schedulern är igång
curl -H "X-Tenant-ID: <tenant>" -H "X-API-Key: <key>" http://localhost:8000/dashboard/control
```

## Kontrollera Scheduler-status

```bash
# Se scheduler-run-mode (manual / scheduled / paused)
GET /dashboard/control

# Sätt till scheduled (aktiverar bakgrundskörning)
PUT /dashboard/control
{"scheduler": {"run_mode": "scheduled"}}

# Sätt till paused (stoppar bakgrundskörning utan att döda appen)
PUT /dashboard/control
{"scheduler": {"run_mode": "paused"}}
```

## Manuell Scheduler-trigger (för test)

```bash
# Trigga en scheduler-pass direkt via API
POST /scheduler/trigger
```

## Logs

Scheduler-events loggas till stdout och till `storage/local_dev/logs/app.log`.

```bash
tail -f storage/local_dev/logs/app.log | grep scheduler
```

## Vanliga Problem

### Schedulern körs inte
1. Kontrollera att `run_mode` är `scheduled` (inte `manual` eller `paused`)
2. Kontrollera att Gmail OAuth-token är giltig (se [runbook-oauth.md](runbook-oauth.md))
3. Kontrollera loggar för `scheduler_pass` eller `inbox_sync` errors

### Dubletter / dubbla jobb skapas
- Plattformen har idempotency-skydd via `gmail_message_id`
- Kontrollera `IntegrationEvent`-tabellen för dubbletter
- Om nödvändigt: pausa schedulern, rensa dubletter, starta om

### SLA-påminnelse körs inte
- Kontrollera att tenantens `auto_actions.lead` inte är `disabled`
- SLA-engine kör max en gång per dygn per tenant (idempotent)
- Se `scheduler_state.last_sla_reminder_at` i tenant-inställningar

## Produktions-Cron (extern)

För produktion rekommenderas extern cron som ett komplement:

```bash
# Trigga inbox-sync var 5:e minut
*/5 * * * * curl -s -X POST \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-API-Key: $API_KEY" \
  https://your-domain.com/scheduler/trigger

# Daily digest kl 07:00
0 7 * * * curl -s -X POST \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "X-API-Key: $API_KEY" \
  https://your-domain.com/scheduler/digest
```

## Återstart

```bash
# Starta om appen (Docker)
docker restart ai-platform

# Kontrollera att schedulern återupptas
curl -H "X-Tenant-ID: <tenant>" ... /dashboard/control
```

## Eskalering

Kontakta plattformsteamet om:
- Schedulern inte startar efter omstart
- Inbox-sync missar mail i > 30 minuter
- SLA-påminnelser skapas inte för uppenbara breach-leads
