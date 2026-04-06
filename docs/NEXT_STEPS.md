# Next Steps

## Mål nu

Målet nu är att gå från fungerande backend-engine till första verkligt säljbara version.

Det som finns nu räcker för att visa teknik och köra kontrollerade live actions. Det som saknas är operatörsyta, ingestion, konfigurerbarhet och paketering.

---

## Phase A – Productize the Operator Surface

### Must do
- bygg minimal admin/dashboard UI
- visa job list
- visa job detail
- visa processor history
- visa actions per job
- visa approvals per job
- visa pending approvals
- approve / reject från UI

### Outcome
Systemet blir körbart av operatör utan Swagger, databas eller kodinsyn.

---

## Phase B – Build Input Connectors

### Must do
- webhook ingestion endpoint
- email ingestion path
- skapa jobs automatiskt från inkommande signaler
- normalisera input till samma job format

### Outcome
Systemet går från “API-driven demo” till faktisk arbetsingång.

---

## Phase C – Move Tenant Config out of Code

### Must do
- tenant config i DB
- provider-val per tenant
- approval channel per tenant
- action defaults per tenant
- workflow toggles per tenant

### Outcome
Nya kunder kan onboardas utan kodändring eller redeploy för varje konfiguration.

---

## Phase D – Add Basic Product Security

### Must do
- enkel auth eller API key per tenant
- säkra read/write endpoints
- skydda approvals och integrationstest
- förbered rollmodell för admin/operator senare

### Outcome
Systemet blir säkrare att ge till extern pilotkund.

---

## Phase E – Harden Real Use Cases

### Lead / sales
- live-testa Monday
- definiera konkret CRM action contract
- säkra end-to-end lead loop

### Finance
- live-testa Visma
- definiera säkra invoice actions
- håll auto-graden konservativ

### Communication
- live-testa Slack fullt
- gör approval channel och notifieringar mer operativa

### Outcome
Plattformen går från generell motor till konkret kundvärde per use case.

---

## Parallel Track – Quality

Detta ska gå parallellt:

- integration tests
- orchestrator tests
- approval lifecycle tests
- repository tests
- tenant isolation tests
- direct integration execution tests

---

## Definition of Done for Next Major Milestone

Nästa större milstolpe är nådd när:

- en operatör kan se jobs, approvals och actions i UI
- ett inkommande event kan skapa job automatiskt
- en tenant kan konfigureras utan kodändring
- Gmail, Slack, Visma eller Monday är live-verifierade i minst ett riktigt flöde
- systemet kan demonstreras som en kontrollerad kundpilot