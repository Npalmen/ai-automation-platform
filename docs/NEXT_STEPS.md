# Next Steps

## Immediate Priority

Målet nu är att gå från tekniskt fungerande backend till första verkligt användbara kundflöde.

---

## Phase A – Close the Lead Loop

### Must do
- koppla `action_dispatch` till verklig CRM- eller notifieringsintegration
- säkra event logging runt verklig dispatch
- definiera tydliga action contracts från decisioning/policy
- verifiera hela lead-flödet end-to-end

### Outcome
Ett lead kan tas emot, förstås, prioriteras och skickas vidare utan manuell handpåläggning när policy tillåter.

---

## Phase B – Build the Operator Surface

### Must do
- enkel UI för job list
- enkel UI för job detail
- approval queue
- manual review queue
- integration event visibility
- audit visibility

### Outcome
Systemet blir körbart av en operatör utan direkt databas- eller kodinsyn.

---

## Phase C – Harden Inquiry Flow

### Must do
- förbättra inquiry processor
- strukturera intent till support / sales / billing
- skapa response-draft eller ticket-dispatch
- förstärk fallback-regler

### Outcome
Plattformen kan användas för fler verkliga kundärenden än enbart leads.

---

## Phase D – Harden Invoice Flow

### Must do
- förbättra AI extraction
- definiera valideringsregler
- approval path för osäkra eller känsliga fall
- säkra att ekonomi-flödet aldrig autoexekverar för aggressivt

### Outcome
Ekonomiflödet blir användbart utan att risknivån blir oacceptabel.

---

## Phase E – Productization

### Must do
- tenant config i DB
- auth / RBAC
- deploymentstandard
- environment strategy
- onboarding-/supportmodell
- bättre dokumentation för drift

### Outcome
Plattformen blir paketerbar som riktig produkt eller managed service.

---

## Parallel Track – Quality

Detta bör gå parallellt med alla faser:

- integration tests
- orchestrator tests
- approval lifecycle tests
- tenant isolation tests
- dispatch tests

---

## Definition of Done for Next Major Milestone

Nästa större milstolpe är uppnådd när:

- lead flow kör verklig dispatch
- approval flow kan användas operativt
- jobb och events kan övervakas via enkel UI eller tydligt API
- testtäckning räcker för säker fortsatt utveckling