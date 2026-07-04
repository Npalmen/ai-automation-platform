> Archived document. Historical reference only. Current governing source is docs/00-master-plan.md.

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
curl -H "X-API-Key: <key>" http://localhost:8000/scheduler/status
```

## Kontrollera Scheduler-status

```bash
# Se scheduler-run-mode (manual / scheduled / paused) och senaste körning
GET /scheduler/status
Header: X-API-Key: <tenant-key>

# Kontrollpanel (automation + scheduler config)
GET /dashboard/control
Header: X-API-Key: <tenant-key>

# Sätt till scheduled (aktiverar bakgrundskörning)
PUT /dashboard/control
Header: X-API-Key: <tenant-key>
Body: {"scheduler": {"run_mode": "scheduled"}}

# Sätt till paused (stoppar bakgrundskörning utan att döda appen)
PUT /dashboard/control
Header: X-API-Key: <tenant-key>
Body: {"scheduler": {"run_mode": "paused"}}
```

## Manuell Scheduler-trigger (för test)

```bash
# Trigga en scheduler-pass för alla tenants direkt via API (kräver admin-nyckel)
POST /scheduler/run-once
Header: X-Admin-API-Key: <admin-key>
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
# Trigga scheduler-pass var 5:e minut (kräver admin-nyckel)
*/5 * * * * curl -s -X POST \
  -H "X-Admin-API-Key: $ADMIN_API_KEY" \
  https://your-domain.com/scheduler/run-once
```

> **Notera:** `POST /scheduler/run-once` kör ett pass för alla aktiva tenants och kräver
> `X-Admin-API-Key`. Extern cron ersätter den inbyggda bakgrundsloopen för
> miljöer med strikta process-restriktioner.

## Återstart

```bash
# Starta om appen (Docker)
docker restart ai-platform

# Kontrollera att schedulern återupptas
curl -H "X-API-Key: <tenant-key>" https://your-domain.com/scheduler/status
```

## Eskalering

Kontakta plattformsteamet om:
- Schedulern inte startar efter omstart
- Inbox-sync missar mail i > 30 minuter
- SLA-påminnelser skapas inte för uppenbara breach-leads
