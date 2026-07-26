---
name: Kundens arbetsyta
overview: Bygg en separat, kundorienterad och initialt read-only arbetsyta ovanpå verifierade tenantisolerade kontrakt utan att duplicera eller påverka besluts-, approval-, dispatch-, Gmail- eller evalflöden.
todos:
  - id: workspace-a-current-truth
    content: Audita befintlig frontend, kundvyer, API-kontrakt och återanvändbara komponenter
    status: completed
  - id: workspace-b-product-contract
    content: Lås informationsarkitektur, routes, roller, vyer och API-kontrakt
    status: completed
  - id: workspace-c-shell-navigation
    content: Bygg kundens appskal, navigation, behörigheter och responsiva grund
    status: completed
  - id: workspace-d-overview
    content: Bygg kundens dagliga översikt och prioriterade arbetslista
    status: completed
  - id: workspace-e-inbox-workflows
    content: Bygg vyer för leads, kundfrågor, approvals och needs-help
    status: completed
  - id: workspace-f-activity-search
    content: Bygg aktivitetshistorik, sökning, filtrering och detaljvyer
    status: completed
  - id: workspace-g-quality-pass
    content: Genomför responsivitet, tillgänglighet, felhantering och UX-kvalitetspass
    status: completed
  - id: workspace-h-closure
    content: Slutverifiera arbetsytan, dokumentera begränsningar och stäng utvecklingsspåret
    status: in_progress
isProject: true
---

# Kundens arbetsyta

## 1. Dokumentets auktoritet

Detta dokument styr utvecklingsspåret för kundens arbetsyta.

Det omfattar inte den interna operatörspanelen under `/ops` och får inte användas för att ändra kärnsystemets beslut, approvals, action dispatch, integrationswrites, Gmail-write-policy eller live-evaluering.

Efter att planen har godkänts är det tekniska innehållet read-only.

Endast följande todo-statusövergångar får göras:

```text
pending → in_progress → completed
```

Det är förbjudet att:

- skriva om mål eller scope i efterhand,
- ta bort stop-gates,
- lägga till produktionswrites i ett frontendkapitel,
- markera en todo som completed utan verifierbar evidens,
- ändra en tidigare completed todo tillbaka till pending eller in_progress.

Nya tekniska beslut som inte ryms i denna plan ska dokumenteras separat och kräver uttryckligt godkännande innan de implementeras.

---

## 2. Produktmål

Kundens arbetsyta ska vara företagets dagliga arbetsyta för den digitala medarbetaren.

När användaren öppnar arbetsytan ska den omedelbart besvara:

1. Vad har hänt?
2. Vad behöver jag besluta?
3. Vilka kunder väntar?
4. Vilka leads är viktigast?
5. Vad har systemet redan gjort?
6. Vad har misslyckats?
7. Vad behöver en människa ta över?

Arbetsytan ska inte kännas som en teknisk adminpanel. Den ska kännas som att företagets digitala medarbetare redan har arbetat, organiserat dagen och förberett de beslut som användaren behöver ta.

Grundprincip:

> Systemet arbetar. Kunden leder.

---

## 3. Första leveransens omfattning

Första sammanhängande leveransen ska vara en kundorienterad, tenantisolerad och initialt read-only arbetsyta.

Den ska kunna visa:

- dagens viktigaste händelser,
- prioriterade arbetsobjekt,
- inkommande leads,
- kundfrågor och supportärenden,
- approvals som väntar på beslut,
- ärenden som behöver mänsklig hjälp,
- utförda aktiviteter,
- planerade eller väntande aktiviteter när verifierad data finns,
- kundvänlig status och historik,
- sökning och filtrering,
- laddnings-, tom-, delvis fel- och fullständigt felläge,
- fungerande desktop-, tablet- och mobilvyer.

Följande ingår inte i den initiala anslutna versionen:

- att godkänna eller avslå approvals,
- att skicka Gmail-svar,
- att återköra actions,
- att ändra automation mode,
- att ändra scheduler,
- att ändra integrationskonfiguration,
- att skapa eller ändra decision records,
- att utföra integrationswrites,
- att ändra tenantpolicy,
- att skapa egna parallella statusmaskiner i frontend.

Sådana funktioner får endast visas som:

- read-only information,
- disabled state,
- read-only preview,
- mockad adapter,
- feature flag som är avstängd som standard.

---

## 4. Verifierad repositorybas som ska återkontrolleras

Repositoryauditen ska utgå från och återverifiera följande nuvarande struktur.

### Operatörsfrontend

Den befintliga frontendapplikationen finns under:

```text
frontend/
frontend/src/
frontend/design/
```

Nuvarande applikation är operatörspanelen och använder:

```text
frontend/src/main.tsx
frontend/src/app/App.tsx
frontend/src/routes/router.tsx
frontend/src/components/operator/
frontend/src/features/
frontend/src/features/auth/
frontend/src/api/
frontend/src/layouts/
frontend/src/styles/
frontend/design/krowolf-ui-profile.json
frontend/design/component-contracts.json
frontend/design/page-contracts.json
frontend/design/contracts.test.mjs
frontend/vite.config.ts
frontend/package.json
```

Nuvarande Vite-konfiguration använder `/ops/` som base path.

Kundarbetsytan får inte oavsiktligt ändra operatörspanelens:

- routing,
- basename,
- autentisering,
- route policies,
- AppShell,
- navigation,
- API-behörigheter,
- produktbeteende.

### Befintlig äldre UI-yta

Följande äldre UI ska auditeras som källa till funktionell historik, men inte användas som automatisk design- eller arkitekturmall:

```text
app/ui/index.html
```

Den ska granskas för:

- befintliga kundvyer,
- befintliga statusöversättningar,
- användbara produktbegrepp,
- tidigare route- och API-användning,
- säkerhetsrisker kring API-nycklar,
- funktioner som redan har tester.

### Befintliga kund- och dashboardkontrakt

Repositoryauditen ska inventera minst:

```text
/tenant
/tenant/context
/customer/account
/customer/activity
/customer/results
/customer/health
/dashboard/summary
/dashboard/roi
/dashboard/leads
/dashboard/support
/dashboard/activity
/dashboard/kpis
/dashboard/operational-insights
/dashboard/sla-breaches
/dashboard/cockpit
/approvals/pending
/jobs
/jobs/{job_id}
/jobs/{job_id}/actions
/jobs/{job_id}/approvals
```

Varje endpoint ska klassificeras som:

- lämplig för direkt återanvändning,
- lämplig efter kundsäker adapter,
- intern och olämplig för kundfrontend,
- blockerad av instabilt parallellt kontrakt,
- skrivande och därmed utanför initial scope.

Auditen ska kontrollera faktisk implementation, tester, tenantisolering, autentisering, pagination, felkontrakt och vilka interna fält som exponeras.

---

## 5. Arkitekturprincip

Kundarbetsytan ska vara en separat produktdomän ovanpå befintliga stabila kontrakt.

Frontend ansvarar för:

- presentation,
- navigation,
- kundvänlig terminologi,
- query state,
- filter state,
- laddnings- och fellägen,
- responsiv layout,
- tillgänglighet,
- read-only interaktion,
- säkra länkar mellan listor och detaljvyer.

Frontend ansvarar inte för:

- beslut,
- riskklassificering,
- policy authorization,
- approval resolution,
- action dispatch,
- action retry,
- integrationswrites,
- Gmail-sändning,
- scheduler,
- serverägd statusövergång,
- tenantidentifiering från användarstyrda värden.

Backend är alltid auktoritativ för:

- tenant,
- roller och behörigheter,
- arbetsobjektets verkliga status,
- vad som är utfört,
- vad som väntar,
- vad som misslyckats,
- vilka handlingar som är tillåtna,
- vilka data som får visas.

---

## 6. Isolerad målstruktur

Den föreslagna canonical kundrouten är:

```text
/app
```

Kundfrontend ska initialt isoleras inom den befintliga frontendpaketeringen genom följande nya namespace:

```text
frontend/src/customer/
frontend/src/customer/app/
frontend/src/customer/api/
frontend/src/customer/auth/
frontend/src/customer/components/
frontend/src/customer/features/
frontend/src/customer/layouts/
frontend/src/customer/routes/
frontend/src/customer/types/
frontend/src/customer/main.tsx
```

Följande separata build-entry får användas om auditen bekräftar att den inte påverkar `/ops`:

```text
frontend/customer.html
frontend/vite.customer.config.ts
frontend/dist-customer/
```

Tillåtna ändringar för customer-build efter godkänt produktkontrakt:

```text
frontend/package.json
frontend/package-lock.json
frontend/tsconfig*.json
frontend/eslint.config.js
```

Dessa får endast ändras när ändringen är nödvändig för kundytan och befintliga operatorgates fortsätter passera.

Generiska komponenter får extraheras till:

```text
frontend/src/components/shared/
frontend/src/lib/
frontend/src/styles/
```

endast när:

- komponenten verkligen är produktneutral,
- operatörsbeteendet inte ändras,
- operatorfrontendens tester och build passerar,
- kundspecifika texter eller behörigheter inte läcker in i shared-lagret.

Kundspecifik kod får inte placeras under:

```text
frontend/src/components/operator/
frontend/src/features/operatorActions/
frontend/src/features/systemStatus/
frontend/src/features/incidents/
```

---

## 7. Backendscope för read-only arbetsyta

Om befintliga endpoints inte ger ett stabilt och kundsäkert kontrakt får ett separat read-only backendområde föreslås:

```text
app/customer_workspace/
app/customer_workspace/__init__.py
app/customer_workspace/router.py
app/customer_workspace/schemas.py
app/customer_workspace/service.py
app/customer_workspace/status_mapping.py
app/customer_workspace/query_models.py
tests/customer_workspace/
tests/test_customer_workspace_*.py
```

Detta område får endast:

- läsa befintliga records och repositories,
- tillämpa tenantfilter,
- mappa serverdata till kundvänliga schemas,
- sammanställa read-only listor och summeringar,
- redigera bort interna eller känsliga fält,
- skapa stabila response envelopes,
- returnera kundvänliga statusar och fel.

Det får inte:

- skriva till databasen,
- skapa audit events,
- lösa approvals,
- skapa execution intents,
- utföra actions,
- återköra jobb,
- göra externa API-anrop,
- påverka scheduler,
- ändra integrationer,
- ändra decision- eller approvalkontrakt.

Föreslagen read-only API-namespace är:

```text
GET /workspace/v1/context
GET /workspace/v1/overview
GET /workspace/v1/work-items
GET /workspace/v1/work-items/{work_item_id}
GET /workspace/v1/approvals
GET /workspace/v1/activity
GET /workspace/v1/health
```

Det slutliga kontraktet ska låsas i:

```text
docs/customer-workspace/api-contract.md
```

En ny router får inte registreras genom ändring i `app/main.py` utan att arbetet först stoppas och uttryckligt godkännande erhålls.

Om repositoryt saknar en befintlig, tillåten routerregistreringspunkt ska detta rapporteras som en stop-gate. Det får inte kringgås med dynamiska importer, monkey patching eller dold route-registrering.

---

## 8. Autentisering och tenantisolering

Kundarbetsytan får aldrig lagra följande i webbläsaren:

- tenant-API-nyckel,
- admin-API-nyckel,
- Gmail-token,
- OAuth refresh token,
- integrationshemligheter,
- signerbara servercredentials.

Förbjudna lagringsplatser omfattar:

```text
localStorage
sessionStorage
IndexedDB
oskyddade cookies
URL query parameters
HTML source
JavaScript build-time constants
```

Operatörens `/auth/admin/*` får inte återanvändas som kundlogin utan separat uttryckligt arkitekturbeslut.

Det anslutna produktionsläget kräver ett verifierat kundautentiseringskontrakt, exempelvis:

- serverägd HttpOnly-kundsession,
- tenant bunden till den autentiserade sessionen,
- SameSite- och Secure-cookie i produktion,
- CSRF-/same-origin-skydd där relevant,
- ingen tenant vald från ett fritt klientfält,
- fail-closed vid saknad eller ogiltig tenant,
- verifierade cross-tenant-tester.

Om detta kontrakt saknas ska kundfrontend köras i:

```text
preview
mock
disabled-connected-mode
```

Den får då inte göra autentiserade produktionsanrop genom en API-nyckel som användaren matar in.

Föreslagna kundroller att utvärdera och låsa:

```text
customer_owner
customer_member
customer_viewer
```

Initial read-only version får ha samma läsrättigheter för rollerna om backendkontraktet ännu inte stödjer säkra skillnader. Framtida writes får inte härledas från frontendrollen utan serververifiering.

---

## 9. Informationsarkitektur

Föreslagen route- och navigationsstruktur:

```text
/app
/app/leads
/app/support
/app/approvals
/app/needs-help
/app/activity
/app/search
/app/work/:workItemId
/app/login
/app/forbidden
```

Kundens synliga huvudnavigation ska som mest innehålla:

- Översikt
- Leads
- Kundfrågor
- Godkännanden
- Behöver hjälp
- Aktivitet

Sökning kan placeras i topbar och ha en separat resultatsida utan att bli ett dominerande primärt menyval.

### Översikt

Översikten ska prioritera:

1. beslut som väntar,
2. kunder eller leads som riskerar att vänta för länge,
3. misslyckade eller blockerade aktiviteter,
4. ärenden som behöver mänsklig hjälp,
5. viktiga nya leads,
6. vad systemet redan har utfört,
7. mindre kritisk aktivitet.

Översikten ska inte prioritera:

- tekniska systemräknare,
- integrationsadapterstatus,
- databasstatus,
- operation UUID,
- interna pipeline states,
- råa audit events.

### Leads

Leadvyn ska kunna visa:

- kontakt eller företag,
- vad leadet gäller,
- prioritet i kundspråk,
- senaste händelse,
- hur länge leadet har väntat,
- nästa förväntade steg,
- om systemet har svarat eller förberett något,
- om mänsklig hantering behövs.

### Kundfrågor

Supportvyn ska kunna visa:

- kund,
- ämne eller kort sammanfattning,
- prioritet,
- nuvarande användarstatus,
- senaste aktivitet,
- väntar på företaget eller kunden,
- om ett svar är förberett, skickat eller blockerat.

### Godkännanden

Initial approvalvy är read-only.

Den ska visa:

- vad systemet föreslår,
- varför ett beslut behövs i kundspråk,
- vem eller vilket ärende det gäller,
- vad som händer efter ett framtida godkännande,
- när förslaget skapades,
- att beslutsknappar ännu inte är aktiva när write-kontraktet är avstängt.

Den får inte anropa approval resolution.

### Behöver hjälp

Vyn ska visa avvikelser där automatiseringen inte kan fortsätta säkert.

Den ska uttrycka:

- vad som har hänt,
- varför systemet har stannat,
- vilken information eller mänsklig bedömning som saknas,
- vilken påverkan det har,
- vad användaren förväntas göra utanför appen om ingen säker appaction finns.

### Aktivitet

Aktivitetsvyn ska tydligt skilja mellan:

- systemet upptäckte något,
- systemet förberedde något,
- systemet väntar på beslut,
- systemet väntar på kund,
- systemet utförde något,
- något misslyckades,
- en människa behöver ta över.

---

## 10. Kundvänligt statuskontrakt

Frontend får inte visa råa backend-enumvärden direkt.

Ett centralt, typat statuskontrakt ska användas.

Föreslagna användarstatusar:

```text
new
prioritized
in_progress
waiting_for_decision
waiting_for_customer
prepared
scheduled
completed
needs_help
failed
cancelled
unknown
```

Föreslagna svenska etiketter:

| Kundstatus | Svensk etikett |
|---|---|
| `new` | Ny |
| `prioritized` | Prioriterad |
| `in_progress` | Hanteras |
| `waiting_for_decision` | Väntar på ditt beslut |
| `waiting_for_customer` | Väntar på kunden |
| `prepared` | Förberett |
| `scheduled` | Planerat |
| `completed` | Utfört |
| `needs_help` | Behöver hjälp |
| `failed` | Kunde inte slutföras |
| `cancelled` | Avslutat |
| `unknown` | Status saknas |

Statusmapping ska ägas av backendkontraktet när en read-only workspace-router finns.

Frontend får endast ha en uttömmande presentationsmapping för redan normaliserade kundstatusar. Den får inte själv försöka tolka en kedja av decision records, execution outcomes eller pipelinehistorik.

Okända värden ska:

- visas säkert,
- inte presenteras som lyckade,
- inte orsaka renderingskrasch,
- kunna identifieras i utvecklingslogg utan att tekniska detaljer visas för kunden.

---

## 11. Kundsäkert datakontrakt

Workspace-API:t ska endast exponera data som behövs för kundens arbetsflöde.

Tillåtna datakategorier:

- kundens eget företagsnamn,
- kontaktuppgifter som företaget redan hanterar,
- ärendesammanfattning,
- kundvänlig kategori,
- prioritet,
- normaliserad status,
- tidsstämplar,
- väntetid,
- kundvänlig aktivitet,
- tydlig fel- eller hjälpsammanfattning,
- verifierad information om utförd eller väntande aktivitet.

Följande får inte exponeras:

- råa prompts,
- fullständiga modelloutputs,
- raw decision records,
- policyinternals,
- interna processorhistoriker,
- stack traces,
- databasnycklar med teknisk innebörd,
- operation UUID som användarbegrepp,
- OAuth-data,
- API-nycklar,
- integrationscredentials,
- råa externa adapterresponses,
- fullständiga okontrollerade payloads,
- andra tenants data.

Ett serverägt, tenantbundet och opakt `work_item_id` får användas för navigation. Det får inte beskrivas som ett jobb-ID eller tekniskt system-ID i UI.

---

## 12. API-response och felkontrakt

Read-only workspace-endpoints ska använda konsekventa envelopes.

Föreslagen princip:

```json
{
  "data": {},
  "meta": {
    "generated_at": "ISO-8601",
    "is_partial": false
  },
  "warnings": []
}
```

Listor ska stödja:

- verifierad tenantisolering,
- stabil sortering,
- `limit`,
- `offset` eller cursorbaserad pagination,
- allowlistade filter,
- allowlistad sortering,
- tydlig total eller `has_more`,
- validerade datumintervall.

Delvis fel ska inte döljas.

Exempel:

- Översiktens prioriterade lista kan visas även om health-blocket saknas.
- Ett påverkat block ska visa ett lokalt felläge.
- Kunden ska informeras om att delar av informationen inte kunde hämtas.
- Ett tekniskt felmeddelande eller stack trace får aldrig visas.

---

## 13. Feature flags och adapters

Följande lägen ska stödjas där relevant:

```text
mock
preview
connected_read_only
connected_actions_disabled
```

Initialt ska alla writes vara avstängda.

Feature flags får inte enbart vara frontendvillkor för säkerhet. Servern ska fortsätta neka otillåtna operationer oavsett frontend.

En mockadapter ska:

- följa samma TypeScript-interface som den framtida API-adaptern,
- ha realistiska svenska fixtures,
- representera laddning, tomt läge, delvis fel och fullständigt fel,
- inte maskera saknade backendkontrakt,
- tydligt markeras som preview i icke-produktionsmiljö.

---

## 14. Design och UX

Designriktning:

- nordisk,
- professionell,
- lugn,
- tydlig,
- arbetsorienterad,
- låg visuell stress,
- hög informationshierarki.

Befintliga designkontrakt under `frontend/design/` ska återanvändas där de är produktneutrala.

Kundytan får komplettera med isolerade kontrakt:

```text
frontend/design/customer-workspace-component-contracts.json
frontend/design/customer-workspace-page-contracts.json
```

Nya tokens får endast införas när befintliga tokens inte täcker ett verifierat behov.

Krav:

- viktig information först,
- högst en eller två tydliga primära handlingar per vy,
- tydlig skillnad mellan förslag, väntande beslut och utfört,
- inga färger som enda informationsbärare,
- tangentbordsnavigation,
- synlig fokusmarkering,
- semantiska rubriknivåer,
- touch targets på minst 44 px,
- fungerande 200 procent zoom,
- inga horisontella sidscrollar,
- läsbara texter utan aggressiv teckenbrytning.

---

## 15. Responsiva brytpunkter

Manuell och automatiserad verifiering ska minst omfatta:

```text
320 px
375 px
768 px
1024 px
1280 px
1366 px
1440 px
1920 px
```

Zoom:

```text
100 %
125 %
150 %
200 %
```

Mobilversionen ska:

- ha användbar navigation,
- visa prioriterade beslut först,
- använda kort eller tydliga rader i stället för hoptryckta tabeller,
- behålla status, kund, väntetid och nästa steg,
- ha fungerande filterpanel,
- kunna öppna detaljvyer utan desktopberoende interaktion,
- undvika hover-only-information.

---

## 16. Filscope

### Tillåtet huvudscope

```text
docs/plans/customer-workspace-plan.md
docs/customer-workspace/**
frontend/src/customer/**
frontend/src/components/shared/**
frontend/src/lib/**
frontend/src/styles/**
frontend/design/**
frontend/customer.html
frontend/vite.customer.config.ts
frontend/package.json
frontend/package-lock.json
frontend/tsconfig*.json
frontend/eslint.config.js
app/customer_workspace/**
tests/customer_workspace/**
tests/test_customer_workspace_*.py
storage/status/customer-workspace-*.md
```

Ändringar utanför detta scope kräver att Cursor först förklarar:

- varför ändringen behövs,
- vilken minsta filändring som krävs,
- varför en isolerad lösning inte fungerar,
- vilken parallell utveckling som kan påverkas.

### Förbjudet scope utan uttryckligt godkännande

```text
app/main.py
app/workflows/action_approval_resolution.py
app/workflows/approval_dispatcher.py
app/workflows/action_dispatch*
app/decisioning/*
app/policies/*
app/evaluation/live/*
```

Dessutom förbjudet:

- testbotens scenariofiler,
- live-eval-workflows,
- approvalkontrakt,
- action authorization-kontrakt,
- execution intent- eller outcome-kontrakt,
- Gmail write-policy,
- Gmail-sändningslogik,
- migrationsfiler,
- produktionsdatabasschema,
- operatorfrontendens säkerhetspolicy.

Förbjudna filer får läsas under audit men inte modifieras.

---

## 17. Branch- och worktreestrategi

Utvecklingsspåret ska utgå från aktuell `origin/main`.

För dokumentationsfasen:

```text
feat/customer-workspace
```

Följande implementationstodos kan använda:

```text
feat/customer-workspace-shell
feat/customer-workspace-overview
feat/customer-workspace-workflows
feat/customer-workspace-activity
feat/customer-workspace-quality
```

Regler:

1. Använd separat worktree när huvudarbetskatalogen har lokala ändringar eller används av parallellt spår.
2. Kör `git fetch origin` före start.
3. Basera ny branch på aktuell `origin/main`.
4. Rebase mot aktuell `origin/main` före varje PR.
5. Kontrollera konflikter mot parallella spår före implementation.
6. Blanda inte flera orelaterade todos i samma PR.
7. Ändra aldrig förbjudna filer för att lösa en rebasekonflikt utan stop-gate.
8. Merge får endast ske efter grön CI och verifierat filscope.
9. Efter merge ska main-SHA och post-merge-resultat rapporteras.

---

## 18. Teststrategi

Tester ska vara riskbaserade och scopeanpassade.

Det är inte ett mål att köra hela testsviten efter varje liten frontendändring. Det är ett mål att köra rätt tester vid rätt gate.

### Basgates för frontend

```text
cd frontend
npm run tokens:generate
npm run typecheck
npm run lint
npm run test:contracts
npm run build
```

När customer-build finns ska motsvarande script läggas till, exempelvis:

```text
npm run typecheck:customer
npm run test:customer
npm run build:customer
```

Operatorbuild och customerbuild ska båda passera när gemensamma filer har ändrats.

### Backendgates

Om `app/customer_workspace/**` skapas:

- targeted workspace-tests,
- tenant isolation,
- cross-tenant denial,
- response schema,
- pagination och filter,
- redigering av interna fält,
- inga databaswrites,
- inga externa anrop,
- okända statusvärden,
- delvis fel,
- tomma resultat.

Full backendregression körs vid större backend-PR eller closure, inte efter varje dokument- eller stylingändring.

### Säkerhetsgates

Verifiera minst:

- ingen tenant-API-nyckel i frontendkoden,
- ingen admin-API-nyckel i frontendkoden,
- ingen authdata i localStorage eller sessionStorage,
- tenant kommer från serververifierad identitet,
- inga interna payloads visas,
- inga andra tenants poster kan hämtas,
- inga write-endpoints anropas,
- inga okända backendstatusar visas som lyckade.

### Browser- och UX-gates

Använd repositoryts befintliga browserharness om ett lämpligt sådant finns.

Inför inte ett tungt nytt browserramverk enbart för detta spår utan att auditen visat att det behövs.

Browserverifiering ska omfatta:

- navigation,
- deep links,
- back/forward,
- laddning,
- tomt läge,
- delvis fel,
- fullständigt fel,
- 401,
- 403,
- 404,
- mobilnavigation,
- filter,
- detaljvy,
- långa svenska texter,
- långa företags- och kundnamn.

---

## 19. Evidens och rapportering

Lokala rapporter ska skrivas till:

```text
storage/status/customer-workspace-*.md
```

De får inte committas.

Varje rapport ska innehålla:

- datum och tid,
- branch,
- base SHA,
- head SHA,
- merge SHA när relevant,
- ändrade filer,
- verifierat filscope,
- utförda kommandon,
- testresultat,
- CI-resultat,
- PR-nummer eller PR-länk,
- post-merge-verifiering,
- upptäckta risker,
- blockerare,
- avvikelser,
- kvarvarande begränsningar,
- explicit PASS, PARTIAL eller BLOCKED.

Inget resultat får beskrivas som PASS utan kommandooutput, CI-evidens eller annan verifierbar grund.

---

# Todo-specifikationer

## workspace-a-current-truth

### Mål

Fastställa repositoryts verkliga nuläge innan produkt- eller implementationbeslut tas.

### Obligatorisk audit

Audita:

- governing docs och read order,
- aktuell main-SHA,
- öppna eller lokala parallella branches när de är åtkomliga,
- operatörsfrontendens struktur,
- routing och Vite base path,
- authprovider och API-klient,
- designkontrakt,
- återanvändbara komponenter,
- legacy-UI,
- befintliga kundvyer,
- samtliga relevanta kund- och dashboardendpoints,
- approval-read-kontrakt,
- job/activity-kontrakt,
- tenantisolering,
- kundsäker statusmapping,
- befintliga tester,
- Docker/build/static serving,
- Caddy/routing,
- CI-workflows,
- möjliga filkonflikter mot huvudspåret.

### Leverabler

```text
docs/customer-workspace/current-truth.md
storage/status/customer-workspace-current-truth.md
```

`docs/customer-workspace/current-truth.md` ska minst innehålla:

- repository-SHA,
- verifierade fakta,
- vilka ytor som är operator, customer, legacy eller shared,
- endpointinventering,
- authinventering,
- testinventering,
- återanvändbara komponenter,
- säkerhetsgap,
- serving- och deploygap,
- konfliktområden,
- rekommenderad teknisk riktning,
- frågor som måste låsas i nästa todo.

### Tillåtet i todo A

- läsa hela repositoryt,
- läsa förbjudna filer,
- skapa eller uppdatera dokumentationsfiler inom customer-workspace-scope,
- ändra todo-status enligt tillåten övergång.

### Förbjudet i todo A

- produktionskod,
- frontendimplementation,
- backendrouter,
- schemaändring,
- dependencyändring,
- buildändring,
- routeändring,
- authändring,
- tester som ändrar systembeteende.

### Tester och gates

- `git diff --check`,
- verifiera giltig YAML-frontmatter,
- verifiera att endast tillåtna dokumentationsfiler är ändrade,
- kontrollera att ingen rapport under `storage/status/` är staged,
- kontrollera att inga förbjudna filer är ändrade.

### Definition of done

Todo A är completed när:

- current-truth-dokumentet är skapat,
- alla obligatoriska auditområden har evidens,
- antaganden är separerade från verifierade fakta,
- auth- och servinggap är tydligt dokumenterade,
- parallella konfliktområden är dokumenterade,
- inga produktionsfiler har ändrats.

### Stop-gates

Stoppa om:

- repositoryt inte motsvarar planens basstruktur,
- kundytan redan byggs i ett parallellt spår,
- en pågående PR ändrar samma planerade namespace,
- aktuellt main inte kan fastställas,
- auditen kräver att lokala ändringar skrivs över.

---

## workspace-b-product-contract

### Mål

Låsa produkt-, informations-, route-, auth-, status-, API- och implementationskontrakt innan kod byggs.

### Leverabler

```text
docs/customer-workspace/product-contract.md
docs/customer-workspace/api-contract.md
storage/status/customer-workspace-product-contract.md
```

### Produktkontraktet ska låsa

- canonical route,
- build- och servingstrategi,
- exakt frontendnamespace,
- exakt tillåtet backendnamespace,
- relationen till `/ops`,
- relationen till legacy-UI,
- navigation,
- vyer,
- detaljvy,
- sökning,
- filter,
- användarroller,
- customer-auth-strategi,
- tenantidentitet,
- feature flags,
- mock- och previewläge,
- statusvokabulär,
- prioriteringsprincip,
- tomma lägen,
- fellägen,
- mobilprincip,
- tillgänglighetskrav,
- vilka komponenter som får återanvändas.

### API-kontraktet ska låsa

För varje endpoint:

- path,
- HTTP-metod,
- autentisering,
- tenantkälla,
- query parameters,
- request schema,
- response schema,
- pagination,
- sortering,
- filter,
- felkoder,
- partial-data-kontrakt,
- vilka befintliga repositories eller tjänster som får läsas,
- vilka fält som förbjuds,
- om endpointen redan finns eller behöver en adapter,
- stabilitet relativt huvudspåret.

Alla initiala workspace-endpoints ska vara `GET`.

### Obligatoriska beslut

Produktkontraktet ska uttryckligen besluta:

1. Om kundfrontend kan ligga i samma frontendpaket utan att riskera `/ops`.
2. Om separat Vite entry ska användas.
3. Om `/app` kan serveras utan förbjuden ändring.
4. Om ett säkert kundsessionskontrakt redan finns.
5. Om connected mode kan byggas eller om shell måste börja i mock/preview.
6. Vilka befintliga endpoints som är tillräckligt kundsäkra.
7. Om ett nytt `/workspace/v1`-lager behövs.
8. Om routerregistrering kräver godkänd ändring i `app/main.py`.
9. Hur `work_item_id` ska representeras utan att exponera intern teknisk betydelse.
10. Hur approvals visas utan att koppla in resolution.
11. Hur delvis datafel presenteras.
12. Vilka exakta tester varje senare todo måste passera.

### Förbjudet i todo B

- produktionsimplementation,
- frontendkomponenter,
- API-klientimplementation,
- backendrouterimplementation,
- authimplementation,
- dependencyändringar,
- write-endpoints,
- databasmigrationer.

### Tester och gates

- `git diff --check`,
- giltig planfrontmatter,
- verifierat docs-only-diff,
- inga motsägelser mellan product contract och API contract,
- alla routes och filpaths ska vara exakta,
- varje blockerad integration ska ha en stop-gate,
- ingen write-operation får finnas i initialt API-kontrakt.

### Definition of done

Todo B är completed när:

- informationsarkitektur är låst,
- canonical route är låst,
- authstrategi är låst eller explicit blockerad,
- API-kontraktet är fullständigt,
- exakt implementeringsscope är fastställt,
- feature flags och mockläge är definierade,
- inga produktionsfiler har ändrats,
- nästa todo kan planeras utan att gissa.

### Övergripande gate efter todo B

Ingen implementation av `workspace-c-shell-navigation` eller senare todo får påbörjas innan:

- rapporten för A och B har granskats,
- current truth har accepterats,
- product contract har accepterats,
- eventuella stop-gates har fått uttryckligt beslut.

---

## workspace-c-shell-navigation

### Mål

Bygga ett isolerat kundappskal utan att ändra operatörspanelens beteende.

### Omfattning

- separat customer entry,
- `/app`-router,
- customer AppShell,
- navigation,
- mobilmeny,
- page container,
- query provider,
- error boundary,
- 401/403/404-sidor,
- previewindikator,
- feature flag-provider,
- mockadapter,
- auth boundary enligt godkänt kontrakt,
- placeholderroutes för låsta vyer.

### Gates

- A och B completed och granskade,
- auth- och servingbeslut godkända,
- inga förbjudna filer behöver ändras,
- operatorbuildens baseline är grön före implementation.

### Tester

- operator typecheck, lint, contracts och build,
- customer typecheck, lint och build,
- route tests,
- navigation tests,
- no-secret-storage test,
- mobilnavigation,
- 401/403/404,
- mock/preview mode.

### Definition of done

- `/ops` fungerar oförändrat,
- customer shell kan byggas isolerat,
- ingen tenantnyckel lagras i klienten,
- alla planerade routes kan nås,
- mobilnavigation är användbar,
- inga produktionswrites finns.

---

## workspace-d-overview

### Mål

Bygga kundens dagliga översikt och prioriterade arbetslista.

### Omfattning

- dagens sammanfattning,
- beslut som väntar,
- viktiga leads,
- kunder som väntar,
- systemets utförda arbete,
- misslyckade aktiviteter,
- behöver-hjälp-poster,
- lokala partial-error states,
- tydligt tomt läge,
- timestamp för senast uppdaterad data.

### Prioriteringsregel

Frontend ska rendera backendens prioriterade ordning.

Frontend får inte skapa egen risk- eller beslutsmotor.

### Tester

- kontraktstest för overview-adapter,
- loading,
- empty,
- populated,
- partial error,
- total error,
- unknown status,
- långa namn,
- mobil och desktop.

### Definition of done

Kunden kan inom några sekunder förstå:

- vad som har hänt,
- vad som kräver uppmärksamhet,
- vad systemet redan har gjort,
- vad som inte gick att slutföra.

---

## workspace-e-inbox-workflows

### Mål

Bygga kundvyer för leads, kundfrågor, approvals och needs-help.

### Omfattning

- leadlista,
- supportlista,
- read-only approvallista,
- needs-help-lista,
- filter,
- sortering,
- pagination,
- summary cards när verifierad data finns,
- länk till gemensam detaljvy,
- disabled future-action states.

### Särskild approvalregel

Ingen approve-, reject-, dispatch- eller Gmail-write-funktion får kopplas in.

### Tester

- listkontrakt,
- tenantisolering där backend ingår,
- filter och pagination,
- okända statusar,
- tomma listor,
- API-fel,
- disabled actions,
- inga write-anrop,
- mobilkort och desktoplayout.

### Definition of done

Varje arbetskö kan förstås utan kunskap om pipeline, decision records eller interna systembegrepp.

---

## workspace-f-activity-search

### Mål

Bygga sammanhängande historik, sökning, filtrering och detaljvyer.

### Omfattning

- aktivitetshistorik,
- global sökning,
- allowlistade filter,
- datumfilter,
- typfilter,
- statusfilter,
- gemensam arbetsobjektdetalj,
- kundvänlig tidslinje,
- tydlig nästa-status,
- deep links,
- back/forward state,
- säkra URL-parametrar.

### Detaljvyn ska visa

- vem eller vad ärendet gäller,
- kort sammanfattning,
- nuvarande kundstatus,
- prioritet,
- vad systemet har gjort,
- vad det väntar på,
- vad som misslyckades,
- när en människa behöver ta över.

Den ska inte visa:

- raw decision record,
- processor history,
- operation UUID,
- adapter payload,
- stack trace,
- rå modelloutput.

### Tester

- search query contract,
- filterkombinationer,
- pagination,
- detalj-404,
- cross-tenant denial,
- tidslinjesortering,
- deep links,
- URL state,
- tom och delvis historik.

### Definition of done

Användaren kan hitta ett ärende, förstå hela kundvänliga historiken och återvända till föregående filterläge.

---

## workspace-g-quality-pass

### Mål

Genomföra ett sammanhängande UX-, responsivitets-, tillgänglighets- och felhanteringspass.

### Omfattning

- samtliga definierade viewportbredder,
- samtliga definierade zoomnivåer,
- tangentbord,
- fokusordning,
- screen reader-labels där relevant,
- kontrast,
- touch targets,
- långa svenska texter,
- långsamma svar,
- stale data,
- partial failure,
- full failure,
- 401/403/404,
- offline-liknande nätverksfel,
- visuell konsekvens,
- tydliga disabled states.

### Tester

- alla targeted frontendgates,
- customerbuild,
- operatorbuild,
- browsermatrix,
- tillgänglighetscheck,
- secret scan,
- no-write network verification.

### Definition of done

Arbetsytan är praktiskt användbar på mobil, tablet och desktop och presenterar inte tekniska fel eller interna systembegrepp för kunden.

---

## workspace-h-closure

### Mål

Slutverifiera utvecklingsspåret, dokumentera ärlig produktstatus och stäng planen.

### Leverabler

```text
docs/customer-workspace/release-notes.md
docs/customer-workspace/known-limitations.md
docs/customer-workspace/verification.md
storage/status/customer-workspace-closure.md
```

### Slutverifiering

Verifiera:

- alla todos completed,
- alla godkända routes,
- customerbuild,
- operatorregression,
- tenantisolering,
- auth,
- no-secret-storage,
- inga writes,
- inga förbjudna filändringar,
- full responsiv matrix,
- tomma lägen,
- partial errors,
- full errors,
- kundvänligt statusspråk,
- dokumenterade begränsningar,
- deploy- och servingstatus,
- post-merge main.

Live Gmail, live dispatch och live approval resolution ska inte köras som del av detta spårs closure.

### Closurestatus

Använd exakt en av:

```text
PASS
PARTIAL
BLOCKED
```

`PASS` kräver att arbetsytan är verifierad i den godkända målmiljön.

`PARTIAL` ska användas om exempelvis:

- endast mock/previewläge är verifierat,
- kundsessionsauth saknas,
- `/app` ännu inte serveras i produktion,
- connected API saknar godkänd routerregistrering.

`BLOCKED` ska användas när ett säkerhets- eller kontraktskrav förhindrar en ärlig leverans.

### Definition of done

Utvecklingsspåret är stängt när:

- slutrapporten innehåller verifierbar evidens,
- begränsningar är dokumenterade utan att döljas,
- inga öppna problem felaktigt beskrivs som färdiga,
- main är verifierad efter merge,
- planens samtliga todo-statusar motsvarar faktiskt resultat.

---

# Globala stop-villkor

Stoppa omedelbart om:

- approvalkontrakt måste ändras,
- action authorization måste ändras,
- action dispatch måste ändras,
- Gmail-write måste införas,
- schedulerlogik måste ändras,
- testbotens filer måste ändras,
- live-eval måste ändras,
- en databasmigration krävs,
- `app/main.py` måste ändras utan godkännande,
- ett säkert kundauthkontrakt saknas för connected mode,
- tenantisolering inte kan verifieras,
- ett större backendområde krävs utanför `app/customer_workspace/**`,
- parallell branch ändrar samma filer eller kontrakt,
- operatörspanelens tester eller build börjar fallera,
- frontend behöver lagra API-nycklar,
- UI:t behöver gissa ett serverbeslut,
- en write behöver döljas bakom en read-only benämning.

Cursor ska då:

1. inte implementera en workaround,
2. dokumentera exakt blockerare,
3. visa minsta möjliga föreslagna kontraktsändring,
4. lista berörda filer,
5. lista risk för parallella spår,
6. skriva en lokal BLOCKED-rapport,
7. stoppa innan produktionskod ändras.
