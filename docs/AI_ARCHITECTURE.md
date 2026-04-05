# AI Architecture

## Core Principle

Alla AI-steg använder:

- Standardiserad runner (`run_ai_step`)
- Typed responses (Pydantic)
- Validation layer
- Fallback handling

---

## run_ai_step

Ansvar:
- LLM call
- parsing
- validation
- fallback
- logging

---

## Prompt System

Alla prompts ligger i:

app/workflows/prompts/

Ex:
- classification.txt
- entity_extraction.txt
- lead_scoring.txt
- decisioning.txt
- invoice.txt
- inquiry.txt

---

## Validation Layer

Regler:
- missing critical → manual_review
- low confidence → manual_review
- duplicate detection → invoice

---

## Processor Pattern

Varje processor:
1. bygger context
2. kör `run_ai_step`
3. returnerar standard payload

---

## Observability

- processor_history
- audit_events
- full trace per job

---

## Designmål

- deterministiskt beteende ovanpå AI
- robust fallback
- enkel att testa
- enkel att expandera