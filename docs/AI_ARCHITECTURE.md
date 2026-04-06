# AI Architecture

## Purpose

AI-lagret ger plattformen förmågan att:

- klassificera inkommande jobb
- extrahera strukturerad data
- scorea och prioritera ärenden
- fatta riktade beslut inför routing och exekvering
- stödja policy- och approval-flöden

Målet är inte “fri AI”, utan kontrollerad AI i en deterministisk workflow-ram.

---

## Core Design Principle

Alla AI-steg ska följa samma modell:

1. bygg processor-specifikt context
2. kalla AI via standardiserad runner
3. validera svaret mot typed schema
4. returnera standardiserad payload
5. degradera säkert vid fel eller låg tillit

---

## AI Building Blocks

### 1. LLM Client
LLM-klienten kapslar anrop till modellen och isolerar AI-kommunikation från processorlogiken.

### 2. Prompt Registry
Prompts hålls centralt så att varje processor använder definierade instruktioner och inte hårdkodad prompttext utspridd i systemet.

### 3. Typed Schemas
AI-svar ska valideras strukturellt, inte bara tolkas löst.

### 4. Fallback Handling
Felaktigt JSON-svar, låg confidence eller schemafel ska inte ge okontrollerad automation.

---

## AI-enabled Processors

Nuvarande AI-centrerade steg i systemet inkluderar minst:

- classification
- entity extraction
- lead scoring / lead processor
- decisioning

Arkitekturen är också upplagd för att utöka invoice och inquiry-flöden med mer AI-tyngd.

---

## Relationship to Workflow Engine

AI fattar inte ensam slutgiltig exekveringsrätt.

Istället gäller:

- AI producerar strukturerad output
- workflow-lagret använder outputen
- policy avgör om automation är tillåten
- approval eller human handoff fångar osäkra fall

Det betyder att AI är en beslutsmotor i delsteg, inte systemets ensamma kontrollpunkt.

---

## Input and Output Contract

Varje AI-processor ska lämna ifrån sig payload som:

- är JSON-kompatibel
- är möjlig att spara i `processor_history`
- kan användas av nästa steg
- kan granskas av människa i efterhand

Detta är centralt för:
- traceability
- debugging
- replay/resume
- policy reasoning

---

## Confidence and Safety

Confidence används som en styrsignal, inte som enda sanning.

Exempel på konsekvenser:
- låg confidence kan ge manual review
- tveksamt case kan ge approval
- schemafel ska trigga fallback
- invalid output får inte trigga automation

---

## Processor Pattern

Varje AI-processor bör följa samma interna struktur:

1. läs relevant historik och input
2. bygg context
3. kör AI-anrop
4. validera schema
5. paketera resultat
6. append till `processor_history`
7. lämna över till orchestrator

---

## Why This Matters

Den här modellen gör att systemet blir:

- testbart
- robust
- utbyggbart
- säkert att automatisera stegvis
- begripligt för både utveckling och drift

Det är avgörande om plattformen ska bli kundbar inom dokumenthantering, lead automation eller supporttriage där felaktig automation annars snabbt blir dyr.