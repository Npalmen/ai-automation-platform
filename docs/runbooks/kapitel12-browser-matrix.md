# Kapitel 12 — Autentiserad browsermatris (pilot)

> **Mål:** Verifiera `/ops` med riktiga server-side sessioner per roll.  
> **Pilot:** `https://api.krowolf.se`  
> **Kör inte** förrän operatören har skapat den skyddade env-filen.

## Säkerhetsregler

- Lägg **aldrig** användarnamn eller lösenord i Git, loggar, rapporter eller screenshots.
- Använd **endast** `/opt/krowolf/.env.browser-test` på pilot (root:root, mode 600).
- **Ingen** testheader eller frontendstyrd roll — endast serverns `ADMIN_ROLE`.
- Scheduler ska vara **pausad** under verifieringen.
- Inga riktiga externa writes — approval-first använder syntetisk `controlled_dispatch` på `T_K12_BROWSER`.

## Förberedelse (operatör)

### 1. Skapa env-fil på pilot

```bash
sudo install -o root -g root -m 600 /dev/null /opt/krowolf/.env.browser-test
sudo nano /opt/krowolf/.env.browser-test
```

Kopiera från `scripts/env.browser-test.example` och fyll i:

```env
K12_BROWSER_BASE_URL=https://api.krowolf.se
K12_BROWSER_USERNAME=<operatör>
K12_BROWSER_PASSWORD=<lösenord>
K12_BROWSER_ROLE=read_only
K12_BROWSER_HEADLESS=true
K12_BROWSER_REPORT_PATH=/opt/krowolf/storage/status/k12_browser_read_only_report.json
```

Spara och verifiera permissions:

```bash
sudo chown root:root /opt/krowolf/.env.browser-test
sudo chmod 600 /opt/krowolf/.env.browser-test
```

### 2. Verifiera env (inga secrets skrivs ut)

```bash
cd /opt/krowolf
sudo python3 scripts/k12_verify_browser_env.py
```

Förväntat: `OVERALL PASS` för fil, mode, variabler, HTTPS-allowlist och roll.

### 3. Installera Chromium (om saknas)

```bash
which chromium || which chromium-browser || which google-chrome
```

Valfritt i env: `K12_BROWSER_CHROME_PATH=/usr/bin/chromium`

## Rollsekvens (global `ADMIN_ROLE`)

Systemet har **en** global operatörsroll. Kör **en roll i taget**:

| Steg | `ADMIN_ROLE` | `K12_BROWSER_ROLE` | Rapportfil |
|------|--------------|-------------------|------------|
| 1 | `read_only` | `read_only` | `k12_browser_read_only_report.json` |
| 2 | `operations` | `operations` | `k12_browser_operations_report.json` |
| 3 | `admin` | `admin` | `k12_browser_admin_report.json` |

### Per roll

1. Sätt `ADMIN_ROLE` i `/opt/krowolf/.env.production` till önskad roll.
2. Starta om **endast** app-containern:
   ```bash
   cd /opt/krowolf
   docker compose restart app
   ```
3. Uppdatera `K12_BROWSER_ROLE` och `K12_BROWSER_REPORT_PATH` i `.env.browser-test`.
4. Verifiera session:
   ```bash
   sudo python3 scripts/k12_verify_browser_env.py
   ```
5. Kör browsermatrisen:
   ```bash
   cd /opt/krowolf
   sudo -E python3 scripts/kapitel12_browser_pilot_verify.py
   ```
6. **Pausa** — granska rapporten i `/opt/krowolf/storage/status/` innan nästa roll.
7. Upprepa för nästa roll.
8. Återställ slutligen avsedd pilotroll i `.env.production` och starta om app.

**Ingen roll är PASS** om `/auth/admin/me` inte returnerar exakt förväntad `role`.

## Aggregera rapporter

När alla tre rollkörningar är klara:

```bash
cd /opt/krowolf
sudo python3 scripts/kapitel12_browser_aggregate.py --status-dir /opt/krowolf/storage/status
```

Skapar `kapitel12_browser_report.json` — **PASS** endast om alla tre rollrapporter är PASS.

## Vad scriptet verifierar

- Login via `/ops/login` (CDP) + session via `/auth/admin/me`
- Sidor: overview, needs-help, customers, customer detail, onboarding, incidents, alerts, alert detail, digests, usage, system
- 7 viewports + zoom 125/150/200 %
- Overflow (`document` och `main`), inga credentials i URL/storage
- Tillgänglighet: skip link, focus-visible, labels
- Rollspecifika API-writes (403/allow enligt policy)
- Approval-first med syntetisk `controlled_dispatch` (reject, stale 409)
- Legacy `/ui` read-only, ingen admin-nyckel i localStorage
- Logout + 401 på `/auth/admin/me`

## Felsökning

| Problem | Åtgärd |
|---------|--------|
| `env incomplete` | Fyll credentials i `.env.browser-test` |
| `session_role_match FAIL` | `ADMIN_ROLE` matchar inte `K12_BROWSER_ROLE` — starta om app |
| `Chromium not found` | Installera chromium eller sätt `K12_BROWSER_CHROME_PATH` |
| `SKIP credentials` | Env-fil saknas eller tom |

## Relaterade filer

| Fil | Syfte |
|-----|--------|
| `scripts/env.browser-test.example` | Icke-hemlig mall |
| `scripts/k12_verify_browser_env.py` | Env-validering utan secrets |
| `scripts/kapitel12_browser_pilot_verify.py` | CDP browsermatris per roll |
| `scripts/kapitel12_browser_aggregate.py` | Samlar rollrapporter |
| `scripts/k12_browser_approval_fixture.py` | Syntetisk approval (tenant-isolerad) |
