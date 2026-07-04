# Master Plan

> **This is the governing document for product direction, execution order and scope control.**
> **If another document conflicts with this file, this file wins.**

---

## Product North Star

Produkten ska bli ett operativt AI-styrsystem för installations- och servicebolag.
Den ska minska administrationen runt bolagets faktiska arbete genom att förstå inkommande information, hämta kontext, guida ärenden rätt, förbereda actions och ge överblick över vad som sker.

**Kort intern definition:**

> Produkten är ett operativt AI-styrsystem för installations- och servicebolag som läser inkommande information, förstår vad som behöver göras, guidar ärenden rätt, förbereder åtgärder i befintliga system och minskar manuell administration runt bolagets faktiska arbete.

**Kort extern kundförklaring:**

> Systemet tar hand om det administrativa mellanrummet mellan mejl, CRM, ekonomi och projekt — så att kunden kan lägga tiden på jobbet de faktiskt säljer.

---

## What the product is

- Ett operativt styrsystem.
- Ett AI-lager mellan mejl, CRM, ekonomi, projekt och support.
- Ett system för att minska små manuell-administrativa moment.
- Ett system som hjälper kunden att läsa, svara, skicka vidare, skapa ärenden, förbereda underlag och följa status.
- Ett system där automation kan vara kundkonfigurerad och riskstyrd.

---

## What the product is not

- Inte en total helhetslösning för alla bolag i första versionen.
- Inte ett nytt ERP.
- Inte en full ekonomiplattform.
- Inte en frontend rewrite.
- Inte en integrationsmarknadsplats med alla system från start.
- Inte en generell chatbot utan operativ styrning.
- Inte fri automatisk bokföring eller externa high-risk actions utan policy/approval.

---

## Target customer

**Primärt:**
- Små och medelstora installations-, service-, el-, solcells- och entreprenadnära bolag.

**Sekundärt (senare):**
- Andra bolagstyper där samma administrationsproblem finns.

---

## First customer strategy

1. Intern testkund.
2. Pilot hos vänner/närstående bolag.
3. Första betalande kund.
4. Presentation mot befintlig leadlista med cirka 200 småföretagare.
5. Fokus på att setup kan göras med initial hjälp, men att fixes därefter ska kunna lösas remote.

---

## Minimum Productable Standard

För första kund måste följande vara sant:

- Anslutningar fungerar.
- Grundarbetena kan utföras.
- Systemet kan läsa, svara och skicka vidare.
- Gmail fungerar som första intake-kanal.
- Admin kan konfigurera kunden.
- Customer UI behöver inte vara full self-service men ska kunna visa enkel status/wow-statistik.
- Integration health ska ge tillräcklig synlighet.
- Failed jobs ska gå att upptäcka.
- OAuth/token-problem ska vara synliga.
- Approval queue ska fungera för riskfyllda actions.
- Admin ska kunna förstå vad som gick fel utan att manuellt läsa råloggar varje gång.

---

## Allowed scope now

Tillåtet före första kund:

- Dokumentationsstyrning.
- Truth audit.
- Stabilisering av befintliga flöden.
- Gmail-intake.
- Ärenden/cases.
- Kundpolicy för automation.
- Approval gates.
- Integration health.
- Failed jobs visibility.
- Pilot readiness.
- Admin-konfiguration.
- Enkel kundvy/wow-statistik.
- Monday/CRM-liknande operationsflöde där det redan finns stöd.
- Fortnox/Visma som read/preview/underlag/approval-gated.
- Fixar som krävs för att befintliga flöden ska fungera produktbart.

---

## Forbidden scope now

Förbjudet före första kund om inte masterplanen ändras explicit:

- React/frontend rewrite.
- Ny frontend-stack.
- Ny stor arkitektur.
- Stora nya integrationer som inte krävs för första kund.
- SSO.
- Billing/self-serve subscription.
- Full marketplace.
- Full ERP.
- Fri automatisk bokföring.
- Massutskick.
- Generell chatbot utan operativ styrning.
- Branschspecifika specialmoduler som inte krävs för första kund.
- Körjournal, resejournal, tidsstämpling och liknande långsiktiga sidospår.

---

## Phase plan

### Fas 0 — Governance Lock
- Skapa styrdokument.
- Rensa dokumentation.
- Uppdatera README/CLAUDE.
- Skapa promptmall.
- Stoppa sidledsglidning.

### Fas 1 — Current Truth Audit
- Kör tester.
- Kontrollera endpoints.
- Kontrollera UI-vyer.
- Kontrollera integrationer.
- Uppdatera `docs/01-current-truth.md`.

### Fas 2 — First Customer Productable Pilot
- Få första interna/pilotkunden i drift.
- Gmail intake.
- Grundärenden.
- Läsa/svara/skicka vidare.
- Admin-konfig.
- Integration health.
- Approval-gated actions där risk finns.
- Enkel kundvy/wow-statistik.

### Fas 3 — Stable Pilot Operations
- Daglig/regelbunden kontroll av failed jobs, tokenhälsa, scheduler, approvals och integrationer.
- Kundfeedback loggas som beslutskandidater, inte direkt som bygguppgifter.
- Fixar prioriteras efter pilotpåverkan.

### Fas 4 — First Paying Customers
- Paketera flöden.
- Förbättra UI där det hjälper sälj/support.
- Skala onboarding från manuell till assisterad.
- Standardisera vanliga kundsetupmönster.

### Fas 5 — Broader Productization
- Mer automation.
- Bättre UI.
- Fler breda integrationer.
- Djupare ekonomi/faktura.
- Sälj/lead-flöden.
- Enklare onboarding.

### Fas 6 — Long-term Expansion
- Körjournal.
- Resejournal.
- Tidsstämpling.
- Fler bolagsområden.
- Branschpaketeringar.

---

## Priority order after first pilot

1. Fler kunder.
2. Mer automation.
3. Bättre UI.
4. Fler integrationer.
5. Faktura/ekonomi.
6. Sälj/lead.
7. Enklare onboarding.

> Notera: Bättre UI får göras tidigare om det direkt hjälper pilot, wow-effekt eller supportbarhet.

---

## Automation risk policy

Automation är tillåten där konsekvensen är reversibel, begränsad och synlig.

Låg-risk actions kan automatiseras per kundpolicy.

Hög-risk actions ska vara approval-gated.

**Hög-risk inkluderar:**
- bokföring
- fakturering
- radering
- kundmeddelanden med juridisk/ekonomisk konsekvens
- avtal
- ändring av ekonomidata
- massutskick
- känsliga externa besked

---

## Integration priority

**Första prioritet:**
- Gmail
- Monday eller befintligt CRM-/operationsflöde
- Fortnox/Visma som read/preview/underlag/approval-gated

**Nästa prioritet:**
- Outlook/Microsoft Mail
- Bred CRM-koppling, exempelvis HubSpot eller Pipedrive

**Inte prioriterat nu:**
- Smala nischintegrationer
- Integrationer som bara en enskild ovanlig kund använder
- Integrationer som kräver stor omskrivning före första kund

---

## Execution governance

**Utförande AI-bottar får:**
- Välja bästa tekniska implementation.
- Fixa uppenbara fel inom uppdragets scope.
- Skapa nya filer om det är tekniskt motiverat.
- Uppdatera dokumentation för vad som faktiskt blivit gjort.

**Utförande AI-bottar får inte:**
- Ändra produktstrategi.
- Ändra fasordning.
- Lägga till nya roadmapspår.
- Bygga sidofunktioner.
- Omprioritera masterplanen.
- Göra större refactor utan uppdrag.
- Ändra riskpolicy.
- Ändra integrationsprioritet.
- Ändra vad som är första kund-scope.

**Om planen verkar fel:**
- Pausa.
- Rapportera problemet.
- Föreslå ändring.
- Genomför inte strategisk ändring.

---

## Change control

Endast masterplanen får ändra riktning. Om en ändring krävs ska den dokumenteras i `docs/07-decisions.md`.

Alla låsta beslut finns i `docs/07-decisions.md` (DEC-001 till DEC-022).

---

## Current next allowed work

Fas 1 — Current Truth Audit:

1. Kör tester och notera faktiskt resultat.
2. Kontrollera endpoints och notera vad som faktiskt fungerar.
3. Kontrollera UI-vyer.
4. Kontrollera integrationshälsa.
5. Uppdatera `docs/01-current-truth.md` med verifierad status.

Se `docs/02-first-customer-plan.md` för go/no-go checklist.
Se `docs/04-execution-rules.md` för hur arbetet ska utföras.
