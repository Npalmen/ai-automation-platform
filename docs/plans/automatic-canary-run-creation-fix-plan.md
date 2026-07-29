---
name: Automatic canary run creation fix
overview: Registrera TBA01 och TBA02 i det allowlistade fixture bundle-kontraktet, härda cleanup-verifieringen och kör exakt en ny automatic Gmail-canary
todos:
  - id: auto-run-fix-a-bundle-audit
    content: Audita manifest, scenario registry, fixture bundles och scenario bundle map
    status: completed
  - id: auto-run-fix-b-registration
    content: Registrera TBA01 och TBA02 med semantiskt korrekta allowlistade fixture bundles
    status: completed
  - id: auto-run-fix-c-contract-gate
    content: Lägg completeness-gate mellan automatic manifest och fixture bundle registry
    status: completed
  - id: auto-run-fix-d-cleanup-verify
    content: Korrigera cleanup-verifieringens environment och fail-closed-beteende
    status: completed
  - id: auto-run-fix-e-tests
    content: Kör riktade tester, full regression och Release Gate
    status: pending
  - id: auto-run-fix-f-delivery
    content: Öppna PR, squash-merga och verifiera post-merge Release Gate
    status: pending
  - id: auto-run-fix-g-canary
    content: Kör exakt en ny TBA01 och TBA02 automatic Gmail-canary
    status: pending
  - id: auto-run-fix-h-stop
    content: Rapportera kvalificering och stoppa före fortsatt automatic expansion
    status: pending
isProject: true
---

# Automatic canary run creation fix

**Source failure:** workflow `30432005515` @ `a03d672`  
**Root cause:** C3 — TBA01/TBA02 missing from `SCENARIO_BUNDLE_MAP`  
**Forensics:** `docs/plans/automatic-canary-run-creation-forensics-plan.md`

Technical content read-only after creation. Only todo status may change.
