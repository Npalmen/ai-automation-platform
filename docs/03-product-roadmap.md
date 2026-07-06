# Product Roadmap

> Governed by `docs/00-master-plan.md`. If this document conflicts with the master plan, the master plan wins.
> Execution agents may reference this roadmap but may not change it without an explicit strategic instruction that updates `docs/00-master-plan.md` first.

---

## Roadmap principles

1. Nothing is built before it is needed for the current phase.
2. Each phase must be complete before the next begins.
3. Long-term items stay in later phases — they do not move forward without an explicit master plan update.
4. Customer feedback during pilot becomes decision candidates in `docs/07-decisions.md`, not direct build items.
5. UI improvements are allowed early only if they directly help pilot, wow-effect or supportability.

---

## Fas 0 — Governance Lock (current)

- Create governing documents.
- Clean documentation.
- Update README and CLAUDE.md.
- Create execution prompt template.
- Stop lateral drift.

**Status:** In progress (this session).

---

## Fas 1 — Current Truth Audit

- Run tests and record actual results.
- Check all endpoints.
- Check all UI views.
- Check integrations.
- Update `docs/01-current-truth.md` with verified status.

**Deliverable:** A trustworthy `docs/01-current-truth.md`.

---

## Fas 2 — First Customer Productable Pilot

- First internal test customer live.
- Gmail intake running.
- Basic cases (lead/support/invoice).
- Read/reply/forward flow.
- Admin config working end-to-end.
- Integration health visible.
- Approval-gated actions where risk exists.
- Simple customer view / wow-statistics.

**Go/no-go:** See `docs/02-first-customer-plan.md`.

---

## Fas 3 — Stable Pilot Operations

- Daily/regular checks of failed jobs, token health, scheduler, approvals and integrations.
- Customer feedback logged as decision candidates, not immediately as build items.
- Fixes prioritized by pilot impact.

---

## Fas 4 — First Paying Customers

- Package flows for sale.
- Improve UI where it helps sales/support.
- Scale onboarding from fully manual to assisted.
- Standardize common customer setup patterns.

---

## Fas 5 — Broader Productization

- More automation.
- Better UI.
- More broad integrations.
- Deeper invoice/finance workflows.
- Sales/lead flows.
- Simpler onboarding.

---

## Fas 6 — Long-term Expansion

> These items are explicitly NOT before first customer.

- Körjournal (mileage log).
- Resejournal (travel log).
- Tidsstämpling (time stamping).
- More company types.
- Industry-specific packages.

---

## Priority order after first pilot

1. Fler kunder.
2. Mer automation.
3. Bättre UI.
4. Fler integrationer.
5. Faktura/ekonomi.
6. Sälj/lead.
7. Enklare onboarding.

> UI improvements may be moved earlier if they directly support pilot effectiveness, wow-effect, or supportability.

---

## Service Profile expansion (future, not Fas 2)

The platform's qualification layer is built around the concept of **service profiles**
(see `app/service_profiles/`). The first version (Fas 2) covers installation and service
companies in the electrical/solar/charger space.

Future expansion to other industries and service families should be done by adding new
service profiles to `app/service_profiles/registry.py` — **not** by changing the core
qualification engine. This keeps the general platform architecture stable while enabling
vertical/niche specialisation.

Examples of future service profile packs (not Fas 2):
- `construction` family: bygg, mark, VVS, ventilation, puts
- `property_service` family: städ, fastighetsskötsel, snöröjning
- `consulting_project` family: IT-konsult, redovisning, juridik
- `generic_business` extensions: bokningshantering, kundservice, webshop

Do not build these until a pilot customer from that vertical provides the requirement.

---

## Integration roadmap

| Integration | Priority | Phase |
|-------------|----------|-------|
| Gmail | First | Fas 2 |
| Monday | First | Fas 2 |
| Fortnox (read/preview/approval-gated) | First | Fas 2 |
| Outlook / Microsoft Mail | Next | Fas 5 |
| HubSpot / Pipedrive | Next | Fas 5 |
| Visma (read/preview/approval-gated) | Later | Fas 5 |
| Narrow niche integrations | Not now | Fas 6 |

---

## Pricing

Pricing strategy belongs in the roadmap but does not block technical first-customer work. Decision tracked in `docs/07-decisions.md` (DEC-022).
