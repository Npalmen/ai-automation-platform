# AI Architecture

## Purpose

AI-lagret ger plattformen förmågan att:

- klassificera inkommande jobb
- extrahera strukturerad data
- prioritera och scorea ärenden
- ge beslutsunderlag till policy och routing
- stödja approval- och human handoff-flöden

Målet är inte autonom AI utan kontrollerad AI i en deterministisk workflow-motor.

---

## Design Principle

Varje AI-steg ska följa samma modell:

1. bygg processor-specifikt context
2. kalla AI via standardiserad runner
3. validera mot typed schema
4. returnera standardiserad payload
5. skriv resultat till `processor_history`
6. degradera säkert vid fel eller låg tillit

---

## Viktig gränsdragning

AI ska inte styra systemflödet direkt.

Det som gäller är:

- AI producerar strukturerad output
- workflow-lagret läser outputen
- policy avgör om automation är tillåten
- approval eller human handoff fångar osäkra fall

Det gör att plattformen förblir testbar, replaybar och spårbar.

---

## AI Building Blocks

### 1. LLM Client
Isolerar modellanrop från processorlogik.

### 2. Prompt Registry
Centraliserar instruktioner per processor.

### 3. Typed Schemas
Tvingar AI-svar till validerbar struktur.

### 4. Fallback Handling
Schemafel, låg confidence eller trasig output får inte leda till okontrollerad automation.

---

## AI-enabled Processors

Nuvarande AI-centrerade steg inkluderar:

- classification
- entity extraction
- lead processor
- decisioning

Invoice och inquiry har arkitekturmässig plats men behöver hårdnas vidare.

---

## Output Contract

Varje AI-processor ska lämna payload som:

- är JSON-kompatibel
- kan sparas i `processor_history`
- kan läsas av nästa steg
- kan granskas i efterhand
- kan ligga till grund för approval, audit och replay

Detta är centralt för:

- traceability
- debugging
- resume
- policy reasoning

---

## Confidence and Safety

Confidence är en styrsignal, inte ensam sanning.

Konsekvenser kan vara:

- låg confidence → manual review
- osäkert case → approval
- schemafel → fallback
- invalid output → ingen automation

---

## Strategic AI Direction

Nästa steg för AI-lagret är inte fler generella features först, utan:

1. högre precision i inquiry triage
2. säkrare invoice extraction
3. bättre testbarhet och evals
4. tydligare contracts mellan AI-output och action-paths

Det viktigaste är att AI:n fortsätter vara kontrollerad och affärsmässigt säker.