# Handoff

## Project
AI Automation Platform — multi-tenant backend-first plattform för AI-driven workflow automation.

## Current objective
Konsolidera dokumentationen och lås officiell MVP-riktning.
Nästa tekniska slice är att verifiera ett officiellt end-to-end backend-flöde:
lead intake → classification → entity extraction → decisioning → policy → approval/resume → Gmail action → audit visibility.

## Read these first
1. docs/02-mvp-scope.md
2. docs/03-system-architecture.md
3. docs/05-current-state.md
4. docs/06-backlog.md
5. docs/07-decisions.md

## What is already true
- Backend foundation exists
- Multi-tenant concept exists via `X-Tenant-ID`
- Workflow/job model exists
- Approval persistence and action persistence exist
- Gmail integration has been live-tested
- Read-endpoints exist for jobs, approvals, actions and audit

## What must not happen
- Do not rewrite the architecture from scratch
- Do not expand scope beyond MVP
- Do not treat all architecture-level integrations as production-ready
- Do not build broad frontend before official backend MVP flow is verified
- Do not let chat history become the source of truth

## Current slice
Documentation consolidation + official MVP flow verification.

## Expected output from next implementation chat
- Identify exact files involved in official lead flow
- Verify or patch end-to-end flow
- Add/update relevant tests
- Produce exact smoke-test instructions
- Propose docs updates after implementation