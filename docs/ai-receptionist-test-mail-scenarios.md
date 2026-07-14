# AI Receptionist — Test Mail Scenarios

> **Purpose:** 8 core test emails that validate the AI Receptionist MVP flow end-to-end.
> Use these when setting up a new test tenant or verifying behavior after a change.
>
> **How to use:** Create these as real Gmail threads, apply the tenant's Gmail label,
> mark unread, then run `/gmail/process-inbox`. Compare actual behavior against expected.

---

## Summary table

| # | Scenario | Expected job_type | Expected behavior | Pending reply? | Sheet tab |
|---|----------|-------------------|-------------------|---------------|-----------|
| 1 | Laddbox hemma | `lead` | Playbook: EV charger, asks main_fuse | Yes (after approval) | Leads |
| 2 | Laddbox fel | `customer_inquiry` | Profile: ev_charger / electrical_fault, asks for error details | Yes (after approval) | Support |
| 3 | Batteri till befintliga solceller | `lead` | Playbook: battery_storage + add_on context | Yes (after approval) | Leads |
| 4 | Solceller producerar dåligt | `customer_inquiry` | Profile: inverter_support / solar, asks for production data | Yes (after approval) | Support |
| 5 | Akut elrisk / luktar bränt | `customer_inquiry` | Emergency — manual_review, no auto-reply | No | Logg |
| 6 | VVS-läcka | `lead` or `customer_inquiry` | Safety/urgency detected — manual_review or asks VVS questions | Conditional | Support/Logg |
| 7 | Bygg/snickarjobb | `lead` | Playbook: building_project, asks property/scope | Yes (after approval) | Leads |
| 8 | Missnöjd kund / complaint | `customer_inquiry` | Complaint override — manual_review, no auto-reply | No | Logg |

---

## Scenario 1 — Laddbox hemma

**Subject:** Offert laddbox hemma

**Body:**
```
Hej,

Jag bor i villa och vill installera en laddbox för elbil i garaget.
Bilen är en Tesla Model 3. Jag vet inte vilken säkring vi har men det är ett äldre hus.

Kan ni ge mig en offert?

Mvh
Erik Lindström
```

| Field | Expected |
|-------|----------|
| job_type | `lead` |
| Playbook | `ev_charger_installation` |
| Context | `new_installation` |
| Questions generated | Asks about main_fuse (säkring), distance panel to charger |
| Does NOT ask | Desired location (suppressed for new install) |
| Approval behavior | Customer reply pending approval (approval-gated) |
| Sheet tab | Leads |
| Quality note | Should NOT say "Hej Niklas" — should say "Hej Erik" |

---

## Scenario 2 — Laddbox fel

**Subject:** Problem med laddboxen

**Body:**
```
Hej,

Vår laddbox hemma slutade fungera igår. Den blinkar rött och vi kan inte ladda bilen.
Vi köpte och installerade laddboxen hos er för ungefär ett år sedan.

Kan ni hjälpa oss?

Mvh
Anna Persson
```

| Field | Expected |
|-------|----------|
| job_type | `customer_inquiry` |
| Profile | `ev_charger_installation` or `electrical_fault` |
| Ticket type | `issue` or `warranty` |
| Questions generated | Asks for error code/blinking pattern, model |
| Approval behavior | Customer reply pending approval |
| Sheet tab | Support |
| Quality note | Warranty detection should fire ("installerade hos er") |

---

## Scenario 3 — Batteri till befintliga solceller

**Subject:** Vill lägga till batteri till solcellerna

**Body:**
```
Hej,

Vi har redan solceller på taket (monterades 2021) och vill nu lägga till ett batterilager.
Är det möjligt? Vilka batterier jobbar ni med?

Vänliga hälsningar
Maria Johansson
```

| Field | Expected |
|-------|----------|
| job_type | `lead` |
| Playbook | `battery_storage` |
| Context | `add_on_existing` (existing solar detected) |
| Questions generated | Asks about inverter brand/model, backup requirement |
| Does NOT ask | Generic property type (should be suppressed) |
| Approval behavior | Customer reply pending approval |
| Sheet tab | Leads |
| Quality note | Must NOT classify as solar_installation — should be battery_storage |

---

## Scenario 4 — Solceller producerar dåligt

**Subject:** Solcellerna verkar inte producera som de ska

**Body:**
```
Hej,

Vi märkte att vår produktion de senaste veckorna är mycket lägre än förra sommaren.
Inga felkoder syns i appen men produktionen är ungefär hälften av vad vi brukar se.

Ni installerade systemet för oss 2022.

Med vänliga hälsningar
Lars Eriksson
```

| Field | Expected |
|-------|----------|
| job_type | `customer_inquiry` |
| Profile | `inverter_support` or `solar_service` |
| Ticket type | `issue` |
| Questions generated | Asks for when issue started, app/error readings, weather comparison |
| Approval behavior | Customer reply pending approval |
| Sheet tab | Support |
| Quality note | Warranty detection should fire ("ni installerade") |

---

## Scenario 5 — Akut elrisk / luktar bränt

**Subject:** AKUT — luktar bränt från elskåpet

**Body:**
```
AKUT!

Det luktar bränt från elskåpet i källaren. Det gnistrar när vi öppnar locket.
Vi har stängt av strömmen till hela huset. Kan ni komma idag?

Ring direkt: 070-123 45 67

/ Familjen Bergström
```

| Field | Expected |
|-------|----------|
| job_type | `customer_inquiry` |
| Profile | `electrical_fault` (high risk) |
| Ticket type | `emergency` or `safety` |
| Urgency | `critical` |
| Approval behavior | **manual_review — NO auto-reply** |
| Sheet tab | Logg (if exported manually) |
| Quality note | Must NOT generate a customer reply. Phone number should be extracted. |

---

## Scenario 6 — VVS-läcka

**Subject:** Läckage i köket

**Body:**
```
Hej,

Vi har ett läckage under diskbänken i köket. Det droppar ganska mycket och vi har lagt
handdukar men det verkar bli värre. Kan ni komma och titta så fort som möjligt?

Med vänlig hälsning
Peter Magnusson
0739-876 543
```

| Field | Expected |
|-------|----------|
| job_type | `customer_inquiry` or `lead` |
| Profile | `vvs_service` |
| Context | `repair_or_fault` |
| Urgency | Medium-high (läckage keyword) |
| Approval behavior | Customer reply pending approval (or manual_review if urgency is critical) |
| Sheet tab | Support (or Logg if manual_review) |
| Quality note | Phone number should be extracted. Should ask about water shutoff access. |

---

## Scenario 7 — Bygg/snickarjobb

**Subject:** Snickeriarbete i huset

**Body:**
```
Hej,

Vi planerar att bygga en altan och samtidigt renovera ett sovrum.
Huset är en villa från 1980-talet. Kan ni ta ett möte och ge en offert?

Vi bor i Järfälla.

Mvh
Sofia och Marcus Lindgren
```

| Field | Expected |
|-------|----------|
| job_type | `lead` |
| Playbook | `building_project` or `carpentry` |
| Context | `new_installation` |
| Questions generated | Asks for timeline, scope details |
| Approval behavior | Customer reply pending approval |
| Sheet tab | Leads |
| Quality note | Address (Järfälla) should be extracted if possible |

---

## Scenario 8 — Missnöjd kund / complaint

**Subject:** Inte nöjd med utfört arbete

**Body:**
```
Hej,

Jag är mycket missnöjd med jobbet som utfördes hos oss förra veckan.
Ni lovade att vara klara på fredagen men kom inte förrän på tisdag, och när
arbetet väl var klart var det slarvigt gjort. Jag vill reklamera arbetet.

Jag förväntar mig att ni hör av er inom 24 timmar.

/ Björn Nilsson
```

| Field | Expected |
|-------|----------|
| job_type | `customer_inquiry` |
| Profile | Complaint override |
| Ticket type | `complaint` |
| Approval behavior | **manual_review — NO auto-reply** |
| Sheet tab | Logg (if exported manually) |
| Quality note | Must NOT ask technical questions. Must NOT auto-reply. Internal handoff should be created. |

---

## How to verify each scenario

After `/gmail/process-inbox` (dry_run=false):

1. `GET /jobs?limit=20` — check `job_type` and `status`
2. `GET /approvals/pending` — check which scenarios have pending replies
3. Review each pending reply body before approving
4. For scenarios 5 and 8: confirm NO pending approval exists (manual_review only)
5. For each job: optionally run `POST /integrations/google-sheets/export-job` and verify tab

**Regression check:** If any complaint or emergency scenario generates a pending auto-reply, that is a regression — do not approve, investigate immediately.
