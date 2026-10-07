# FEAT-076: Invoice reconciliation, Meter's billed cost against the provider's invoice

| Field | Value |
| --- | --- |
| Sub project | P10 |
| Status | Specified |
| Specification | [P10 spec](../specs/2026-10-07-p10-proven-numbers-design.md), sections 5.3 to 5.5, 6 and 7 |
| Tasks | TASK-P10-003, TASK-P10-004, TASK-P10-005 |
| Refresh cadence | Daily, the `invoices` row in `collector_schedule` |

## What it does

Reads each AWS invoice for the payer, keeps it with its issue date and the time Meter read
it, and compares it with the sum of Meter's billed cost for that invoice, before tax and tax
apart, in the invoice's currency. Each comparison is Matched, Mismatched with the difference
shown, Period open, No rows, Currency differs, or Not readable with its typed cause. The
result is on its own screen and on the FinOps practitioner's Overview, labelled measured.

## Why it exists

Meter's central claim is that every figure says how far it can be trusted, and nothing yet
checks its totals against what AWS bills. FOCUS 1.4, ratified on 2026-06-04, adds invoice
reconciliation to the standard, and the market research of 2026-10-07 found no competitor
publishing how closely its numbers match the invoice. A match rate on the front page turns
the claim into a figure anyone can check.

## How it works

A port in `finops_core` names the read; a fake answers in tests and an AWS adapter calls the
Invoicing API's `ListInvoiceSummaries` through the credential broker. The `invoices`
collector writes `billing_period` and `invoice_detail` rows at the grain of a whole invoice,
because AWS returns no line items. Each cost row carries the `invoice_id` its row in AWS's
FOCUS export names, so the comparison is a sum over the rows of one invoice, computed when it is read so
it cannot drift from either side. The tolerance is 0.01 percent of the invoice, modelled, a
named constant to revisit once a real invoice has been compared.

## Failure behaviour

A read that fails is Not readable with its typed cause, AccessDenied, Throttled, NotOptedIn
or NoData, and never a zero or a match. A billing period with no issued invoice is Period
open, not a mismatch. An invoice whose id no cost row carries is No rows. Rows in another
currency are Currency differs and are never converted. One invoice failing to read never
fails the run.

## Security considerations

An invoice totals every account under the payer, so the guard's `PayerWide` rule confines it
to a reader whose scope covers the whole payer, as budgets are by ADR-0025; a narrower reader
gets a typed refusal and no total. The reader role gains `invoicing:ListInvoiceSummaries`
and nothing that writes, constraint 6. Invoice amounts are financial data of the tenant and
are classified in `docs/09-DATA-CLASSIFICATION.md` when the tables land.

## Interface

- `GET /api/v1/cost/reconciliation?period=YYYY-MM`, an envelope of comparisons, exportable.
- The Invoice reconciliation screen at `/report/reconciliation`.
- The Matches the invoice tile on the FinOps practitioner's Overview.
- Through the MCP server, as every route is, constraint 8.

## Not doing

Invoice line items, because AWS's summary API has none. Invoices from any provider but AWS.
Converting between currencies. Deciding when a closed period is final, which is OPEN-08.
