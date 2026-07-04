# Decisions

Each decision records a locked product or execution decision. Execution agents may reference decisions but may not change them unless explicitly instructed by the user via a master plan update.

> Historical technical ADRs (DEC-001 to DEC-006 from earlier sessions) are preserved in `docs/archive/legacy-07-technical-decisions.md`.

---

## DEC-001 — Product category

**Status:** Locked  
**Decision:** The product is an operational AI control system for installation and service companies.  
**Reason:** This is the chosen product direction.  
**Consequence:** Features must support operational control, not generic chatbot behavior.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-002 — Core value proposition

**Status:** Locked  
**Decision:** The product shall reduce administrative work around the company's actual occupation.  
**Reason:** Customers should spend time on their core work, not administration.  
**Consequence:** Features that add administrative overhead rather than remove it are out of scope.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-003 — First customer strategy

**Status:** Locked  
**Decision:** First customer strategy is: internal test → friends/pilot → paying customer → lead list presentation.  
**Reason:** Risk-controlled entry to market. Learn before selling broadly.  
**Consequence:** Do not optimize for self-serve before the first paying customer.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-004 — Scope of first version

**Status:** Locked  
**Decision:** The first version shall not be a total complete solution for all niche companies.  
**Reason:** Scope must be contained to ship quickly and learn from real use.  
**Consequence:** Narrow niche features are out of scope until explicitly decided.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-005 — Task-driven system

**Status:** Locked  
**Decision:** The system shall be task-driven, not a single linear workflow.  
**Reason:** Different case types (lead/support/invoice) need different flows.  
**Consequence:** Architecture must support multiple pipelines, not one monolithic flow.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-006 — Automation risk control

**Status:** Locked  
**Decision:** Automation is allowed early but risk must be limited through customer policy, approval gates, and limited external actions.  
**Reason:** Customer trust depends on controlled, reversible automation.  
**Consequence:** High-risk actions must be approval-gated. Low-risk actions may be configured per customer.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-007 — Admin config is sufficient for first version

**Status:** Locked  
**Decision:** Admin configuration is sufficient for the first version. Full self-service onboarding is not required before first customer.  
**Reason:** Simpler to ship; customers can be onboarded with assistance.  
**Consequence:** Self-service onboarding is a later-phase feature.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-008 — Customer UI wow-statistics

**Status:** Locked  
**Decision:** Pilot customer UI should show wow-statistics, especially saved time and status.  
**Reason:** Demonstrates value visibly to the customer.  
**Consequence:** ROI/dashboard view is required for pilot. Deep analytics are not.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-009 — Primary integration areas

**Status:** Locked  
**Decision:** Primary integration areas are mail, economics/finance, and CRM/operations.  
**Reason:** These cover the core administrative friction for the target customer.  
**Consequence:** Integrations outside these areas are deprioritized.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-010 — Broad integrations before narrow

**Status:** Locked  
**Decision:** Broad integrations are prioritized before narrow niche integrations.  
**Reason:** Broad integrations serve more customers; narrow ones serve edge cases.  
**Consequence:** Do not build a narrow niche integration before broad coverage is adequate.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-011 — Execution agents choose technical path

**Status:** Locked  
**Decision:** Execution bots may choose the best technical path but may not change product strategy, prioritization or roadmap.  
**Reason:** Technical decisions belong to the execution agent; strategic decisions belong to the master plan.  
**Consequence:** Any strategic change must go through master plan update and this decisions log.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-012 — Pause and report on plan issues

**Status:** Locked  
**Decision:** If a bot discovers the plan appears wrong, it shall pause and report, not adjust the plan itself.  
**Reason:** Prevents uncontrolled strategic drift by execution agents.  
**Consequence:** Execution agents have a defined stop condition; see `docs/04-execution-rules.md`.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-013 — Aggressive documentation cleanup before building

**Status:** Locked  
**Decision:** Documentation shall be cleaned aggressively before continued building, but without losing verified technical history.  
**Reason:** Stale conflicting docs cause execution agents to drift.  
**Consequence:** Old docs go to archive; new governing structure is the source of truth.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-014 — Keep existing codebase

**Status:** Locked  
**Decision:** The current codebase is kept. No major rewrite before first customer.  
**Reason:** Rewriting delays shipping and destroys verified working behavior.  
**Consequence:** Improve incrementally; refactor only what is broken and within task scope.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-015 — Frontend only where needed for pilot

**Status:** Locked  
**Decision:** Frontend is improved only where needed for pilot, wow-statistics and understandability. No new frontend stack before first customer.  
**Reason:** Frontend stack change introduces large risk and scope creep.  
**Consequence:** Single-file `app/ui/index.html` (vanilla HTML/CSS/JS) remains the frontend. No React, Vite, Tailwind.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-016 — No new large integrations before first customer

**Status:** Locked  
**Decision:** New large integrations are forbidden before first customer, except integrations required for the chosen first customer.  
**Reason:** Integration work is large scope; must be deferred until customer needs are confirmed.  
**Consequence:** Only Gmail, Monday and Fortnox/Visma read-only are in scope for first customer.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-017 — Automatic actions allowed if low-risk and reversible

**Status:** Locked  
**Decision:** Automatic external actions are allowed if they are customer-configured, low-risk and reversible. High-risk actions shall be approval-gated.  
**Reason:** Automation must be safe and controllable.  
**Consequence:** See automation risk policy in `docs/00-master-plan.md`.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-018 — Fortnox/Visma read/preview/approval-gated

**Status:** Locked  
**Decision:** Fortnox and Visma shall initially be read/preview/underlag/approval-gated. Not free bookkeeping automation.  
**Reason:** Bookkeeping errors are high-risk and hard to reverse.  
**Consequence:** Any Fortnox write path must go through an approval gate. Dry-run preview is always available without write.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-019 — Gmail first intake channel

**Status:** Locked  
**Decision:** Gmail is the first prioritized intake channel because it already exists in the repo. Outlook/Microsoft Mail comes next.  
**Reason:** Existing implementation is the fastest path to first customer.  
**Consequence:** Do not build Outlook intake before Gmail is stable in pilot.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-020 — Monday as primary operations channel

**Status:** Locked  
**Decision:** Monday is the primary operations/project channel until another CRM/operations system is chosen for a paying customer.  
**Reason:** Monday integration is already live-verified.  
**Consequence:** Build Monday depth before broad CRM expansion.  
**Can change if:** First paying customer explicitly requires a different system.

---

## DEC-021 — Krowolf brand retained

**Status:** Locked  
**Decision:** Krowolf is used until further notice technically. Brand rename is out of scope before first customer.  
**Reason:** Brand work is a distraction from shipping.  
**Consequence:** All technical references to Krowolf remain unchanged until a brand decision is made.  
**Can change if:** A separate strategic brand decision is made.

---

## DEC-022 — Pricing in roadmap but not blocking

**Status:** Locked  
**Decision:** Pricing strategy shall be added to the roadmap but shall not block technical first-customer work.  
**Reason:** Price discovery happens through pilot; it should not delay shipping.  
**Consequence:** First customer may be unpaid/pilot. Pricing model is defined in a later decision.  
**Can change if:** A separate pricing decision is made and documented here.
