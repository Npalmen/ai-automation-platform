# Google Sheets — Leads & Support Structure (Mårtens Demo)

> **Status: MANUAL DEMO STEP — integration not yet implemented**
>
> The platform does not currently have a Google Sheets integration.
> For the demo, this is a manual output step: copy extracted job fields
> from the API response into the sheet to demonstrate the expected output.
>
> When the integration is built, this document defines the target structure.

---

## Recommended sheet name

```
Krowolf - Mårtens Demo
```

---

## Tabs

| Tab | Purpose |
|-----|---------|
| **Leads** | New business opportunities — classified as `lead` job type |
| **Support** | Existing customer service requests — classified as `customer_inquiry` |
| **Logg** | Audit log — all demo runs with timestamp, job count, and operator |

---

## Tab: Leads — Column headers

| Column | Header | Notes |
|--------|--------|-------|
| A | Datum | ISO date when the job was created: `YYYY-MM-DD` |
| B | Job-ID | Krowolf internal job UUID (for traceability) |
| C | Avsändare | Extracted sender name from AI |
| D | E-post | Sender email address |
| E | Telefon | Extracted phone number (if present) |
| F | Ort | Extracted location/city |
| G | Tjänst | Extracted service type (e.g. "elcentralbyte", "laddbox 11kW") |
| H | Prioritet | Extracted priority: Kritisk / Hög / Medel / Låg |
| I | Sammanfattning | AI-generated summary (max 200 chars) |
| J | Nästa steg | Suggested next action from AI |
| K | Svarsutkast | First 200 chars of the draft response |
| L | Status | Manual: Ny / Kontaktad / Offert skickad / Vunnen / Förlorad |
| M | Anteckningar | Manual free-text notes |

---

## Tab: Support — Column headers

| Column | Header | Notes |
|--------|--------|-------|
| A | Datum | ISO date |
| B | Job-ID | Krowolf internal job UUID |
| C | Avsändare | Extracted sender name |
| D | E-post | Sender email |
| E | Telefon | Phone (if extracted) |
| F | Ort | Location (if extracted) |
| G | Ärendetyp | Issue type (e.g. "vattenläcka", "säkringsavbrott", "solcellsservice") |
| H | Prioritet | Kritisk / Hög / Medel / Låg |
| I | Brådskande | Ja / Nej |
| J | Sammanfattning | AI summary |
| K | Nästa steg | Suggested action |
| L | Godkännandestatus | Pending / Approved / Rejected |
| M | Status | Manual: Öppen / Under arbete / Löst / Stängd |
| N | Anteckningar | Notes |

---

## Tab: Logg — Column headers

| Column | Header | Notes |
|--------|--------|-------|
| A | Tidsstämpel | `YYYY-MM-DD HH:MM:SS` |
| B | Operator | Who ran the sync |
| C | Demo-körning | Demo run ID or label |
| D | Antal jobb | Number of jobs created |
| E | Query-använd | Gmail query used |
| F | Kommentar | Free text |

---

## Example rows: Leads tab

| Datum | Job-ID | Avsändare | E-post | Telefon | Ort | Tjänst | Prioritet | Sammanfattning | Nästa steg | Svarsutkast | Status | Anteckningar |
|-------|--------|-----------|--------|---------|-----|--------|-----------|----------------|------------|-------------|--------|--------------|
| 2026-07-08 | `abc-123` | Lars Eriksson | lars.eriksson.demo@example.com | 070-123 45 67 | Sollentuna | Elcentralbyte | Hög | Villa från 70-talet, gammal elcentral, brandrisk nämns. | Boka besiktning | Hej Lars, vi tar ditt ärende på allvar… | Ny | Scenario 1 |
| 2026-07-08 | `abc-124` | Mikael Svensson | mikael.svensson.demo@example.com | — | Lidingö | Laddbox 11kW | Medel | Vill ha hemmaladdbox för Tesla, fristående garage 20m. | Skicka offert | Hej Mikael, vi installerar laddboxar… | Ny | Scenario 3 |
| 2026-07-08 | `abc-125` | Erik Persson | erik.persson.demo@example.com | 073-222 33 44 | Danderyd | Solceller 8-10 kWp | Hög | Befintlig kund, tidigare laddbox, nu solceller. | Boka hembesök direkt | Hej Erik, välkommen tillbaka! | Ny | Scenario 11 |

---

## Example rows: Support tab

| Datum | Job-ID | Avsändare | E-post | Telefon | Ort | Ärendetyp | Prioritet | Brådskande | Sammanfattning | Nästa steg | Godkännandestatus | Status | Anteckningar |
|-------|--------|-----------|--------|---------|-----|-----------|-----------|-----------|----------------|------------|-------------------|--------|--------------|
| 2026-07-08 | `abc-126` | Anna Lindqvist | anna.lindqvist.demo@example.com | 076-987 65 43 | Täby | Strömbortfall / säkringsfel | Kritisk | Ja | Barn hemma, halva huset utan ström sedan idag. | Eskalera till jourtekniker | Pending | Öppen | Scenario 2 — AKUT |
| 2026-07-08 | `abc-127` | Helena Berg | helena.berg.demo@example.com | 070-555 11 22 | Södermalm | Vattenläcka | Hög | Aktiv läcka under diskbänk, hink satt ut. | Boka besök 1-2 dagar | Pending | Öppen | Scenario 6 |
| 2026-07-08 | `abc-128` | Maria Gustafsson | maria.gustafsson.demo@example.com | — | Okänd | Okänt elfel | Hög | Brådskande men ofullständig — saknar adress och detaljer. | Kontakta för mer info | Pending | Öppen | Scenario 10 |

---

## Safe configuration notes

> **These rules must be followed whenever a real Google Sheets integration is added.**

1. **Never commit the Google Sheet ID to the repository.**
   Store it as an environment variable only:
   ```bash
   DEMO_GOOGLE_SHEET_ID=your-sheet-id-here  # In .env.demo — never in .env.example or repo
   ```

2. **Use read-only access by default.** Write access only to this specific demo sheet.

3. **Isolate demo writes to this sheet.**
   When the integration is built, the Sheet ID must be tenant-scoped config —
   writing to another tenant's sheet must be prevented at the platform level.

4. **Do not write to any customer-owned Google Sheet during the demo.**

5. **Do not share the Sheet ID in chat, commits, or support tickets.**

6. **Demo sheet access:** Share with Mårten's Gmail only + operator Google account.
   Do not make it publicly accessible.

---

## Manual demo step instructions (for now)

Since the integration is not yet implemented, follow these steps during the demo:

1. After running `POST /gmail/process-inbox`, collect the job response:
   ```bash
   curl -sS "https://api.krowolf.se/jobs?limit=20" \
     -H "X-API-Key: DEMO_TENANT_KEY" | python3 -m json.tool
   ```

2. For each job in the response, copy these fields manually into the Sheet:
   - `job_type` → tab selection (lead → Leads, customer_inquiry → Support)
   - `classification.extracted_fields` → fill columns
   - `pipeline_result.summary` → Sammanfattning
   - `pipeline_result.suggested_action` → Nästa steg
   - `pipeline_result.draft_response[:200]` → Svarsutkast

3. Show the Sheet to the customer as the "output surface" and say:
   > "This data is already classified and extracted by the AI — writing it to your
   > spreadsheet automatically is the next integration we're completing."

---

## When Google Sheets integration is built

Add to `app/integrations/enums.py`:
```python
GOOGLE_SHEETS = "google_sheets"
```

Add to `app/integrations/registry.py` IMPLEMENTED_INTEGRATIONS when the adapter is ready.

Add to `env.example`:
```bash
# Google Sheets integration (when implemented)
# GOOGLE_SHEETS_CREDENTIALS_JSON=   # service account JSON path, never commit
# DEMO_GOOGLE_SHEET_ID=             # demo sheet ID, never commit
```

The adapter should enforce:
- One Sheet ID per tenant (stored in tenant config or env)
- Write-only to configured sheet; no cross-tenant sheet access
- Fail closed: if Sheet ID is missing, log and skip — do not error the main job pipeline
