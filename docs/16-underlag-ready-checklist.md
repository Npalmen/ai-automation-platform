# Underlag Ready Checklist — Invoice/Bookkeeping Preparation

This checklist defines what "underlag redo" (preparation ready) means in the platform. A case/job is considered to have ready invoice/bookkeeping preparation when the following criteria are met.

## Required conditions

1. **Job completed** — job status is `completed` (pipeline has finished)
2. **Finance draft available** — `POST /finance/invoices/{job_id}/draft` returns a valid draft with:
   - `amount_ex_vat` is not null/zero
   - `vat_rate` is determined (0, 6, 12, or 25)
   - `expense_category` is assigned
3. **Customer identified** — at least one of: customer name, email, or organization number is present in job data or operations workspace

## Recommended conditions (strengthen underlag quality)

4. **Operations workspace populated** — `operations_workspace` exists with non-default project/work_order data
5. **Work order completed** — `operations_workspace.work_order.status == "completed"`
6. **Delivery package ready** — `operations_workspace.delivery_package.status` is `"ready"` or `"sent"`
7. **Material/time documented** — if applicable, `operations_workspace.finance` contains material or labor entries
8. **Fortnox preview successful** — `POST /finance/invoices/{job_id}/fortnox/preview` returns without error

## Not required (outside platform scope)

- Actual bookkeeping posting in Fortnox
- Full attestation chain
- VAT filing
- Payroll/salary handling

## KPI definition

The dashboard KPI "Fakturaunderlag redo" counts jobs where:
- `job_type` is `"invoice"` OR `job_type` is `"lead"`/`"customer_inquiry"` with `operations_workspace.work_order.status == "completed"`
- Job `status` is `"completed"`
- The job has NOT been exported to Fortnox (no `integration_events` row with `event_type` containing `"fortnox"` for this job)

This gives operators a count of cases that are ready for invoice preparation but have not yet been pushed to the accounting system.
