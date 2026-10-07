# P10 Proven numbers, FOCUS 1.4 and invoice reconciliation: design specification

Date: 2026-10-07
Status: Delivered on 2026-10-08 against fakes, section 12. Approved by the owner on 2026-10-07 as priority 2 of `next-in-scope.txt`, CHG-0122. The design choices below carry their recommendation; OPEN-21 was withdrawn the same day, section 5.2
Sub project: P10
Features: FEAT-076, and a change to FEAT-004
Depends on: P1 delivered. Proof against a real bill waits on ISS-002 and ISS-003, an AWS account and its billing export, and on TASK-P9-001, the hub's network path, ISS-242
Supersedes: nothing
Order: runs before P9, by the owner's priority of 2026-10-07. It is numbered P10 because P9 was already specified

## 1. Purpose

Meter's central claim is that every figure says how far it can be trusted. Nothing yet
checks its totals against what AWS bills. FOCUS 1.4, ratified on 2026-06-04, adds invoice
reconciliation to the standard, and the market research of 2026-10-07 found no competitor
publishing how closely its numbers match the invoice. P10 gives Meter's cost row the
columns FOCUS 1.4 makes mandatory and the two that tie a row to its invoice, reads AWS's
invoices, and shows how closely Meter's billed cost matches each one, as a measured figure.

## 2. Definition of done

- Meter's cost row carries every column FOCUS 1.4 makes Mandatory for Cost and Usage, and
  `InvoiceId` and `InvoiceDetailId`.
- `ProviderName`, which FOCUS 1.3 replaced with `ServiceProviderName`, is carried into that
  column and into `HostProviderName`, without breaking a running version: added and
  backfilled in P10, with `ProviderName` and `PublisherName`, which 1.4 removes, dropped in a
  later release, constraint 12.
- Each AWS invoice is read with its two timestamps and compared with the sum of Meter's
  billed cost for that invoice, before tax and tax apart, in the invoice's currency.
- Every comparison has a typed state, and a failure is never shown as a zero.
- The match shows on its own screen and on the FinOps practitioner's Overview, labelled
  measured, with `as_of` and `collected_at`.
- Everything is built and tested against fakes. The comparison against a real invoice is
  recorded as waiting on ISS-002, ISS-003 and TASK-P9-001.

## 3. Out of scope

- The conditional and recommended FOCUS 1.4 columns no source of Meter's fills yet, listed
  in section 4. They come with FOCUS conformance, `next-in-scope.txt` section 8.
- The Contract Commitment dataset. It belongs with commitments, proposal 5.
- Asking AWS for a FOCUS 1.3 or later export. When one exists, its own provider columns
  replace the derivation in section 5.2.
- Invoice line items. AWS's `ListInvoiceSummaries` returns none, so Meter's Invoice Detail
  rows are at the grain of a whole invoice.
- Any provider but AWS.

## 4. The gap, measured on 2026-10-07

Computed from the 65 columns of FOCUS 1.4's Cost and Usage dataset and the columns of
`cost_focus_daily` in `finops_api/db/models.py`. Every count here is measured.

| Kind | FOCUS 1.4 | Meter's row | Missing |
| --- | --- | --- | --- |
| Mandatory columns | 21 | 15 | `BillingAccountName`, `BillingCurrency`, `ChargeClass`, `HostProviderName`, `PricingUnit`, `ServiceProviderName` |
| Columns that tie a row to its invoice | 2 | 0 | `InvoiceId`, `InvoiceDetailId` |
| Columns FOCUS 1.4 removes | 0 | 2 | Meter still stores `ProviderName` and `PublisherName` |
| Datasets | 4 | 1 | Billing Period and Invoice Detail in P10; Contract Commitment later |

Conditional or recommended columns no source of Meter's fills yet, left for FOCUS
conformance: `AllocatedMethodDetails`, `AllocatedMethodId`, `AllocatedResourceId`,
`AllocatedResourceName`, `AllocatedTags`, `BillingAccountType`, `CapacityReservationId`,
`CapacityReservationStatus`, `ChargeFrequency`, `CommitmentDiscountCategory`,
`CommitmentDiscountName`, `CommitmentDiscountQuantity`, `CommitmentDiscountUnit`,
`CommitmentProgramEligibilityDetails`, `ContractApplied`, `ContractedUnitPrice`,
`ListUnitPrice`, `PricingCategory`, `PricingCurrency` and its three prices, `RegionName`,
`ResourceType`, `ServiceSubcategory`, `SkuMeter`, `SkuPriceDetails`, `SkuPriceId`,
`SubAccountName`, `SubAccountType`. Meter's EKS split columns, FEAT-035, are its own
extension and stay beside the FOCUS 1.3 `Allocated` columns until a source fills those.

FOCUS 1.4's dataset attributes map onto what Meter already keeps: recency is `as_of` and
`collected_at` on every row, constraint 10, and completeness is the run ledger's PARTIAL.

## 5. Decisions

### 5.1 The canonical schema is FOCUS 1.4, ADR-0034

Constraint 2 named FOCUS 1.1. P10 moves Meter's row to FOCUS 1.4's mandatory columns and
its invoice columns, and constraint 2's text changes in TASK-P10-006, when the code carries
it, not before. Each newly ratified version gets a gap note like section 4 within a month.

### 5.2 The source is AWS's FOCUS export, read where each column is present

Meter already reads AWS's FOCUS export through Athena, `finops_providers/aws/cur.py`, by
FOCUS column names; it has never normalised raw CUR 2.0 itself. AWS's FOCUS 1.2 export,
generally available since 2025-11-19, carries `BillingAccountName`, `BillingCurrency`,
`ChargeClass`, `PricingUnit` and `InvoiceId`. Each is read when the export's table has it,
asked of the catalog as the split columns already are, so an older export reads as before
with those columns null rather than failing.

`ServiceProviderName` and `HostProviderName` arrive with FOCUS 1.3, which no AWS export
offered on 2026-10-07, so P10 derives them. FOCUS introduced `ServiceProviderName` as the
replacement for `ProviderName`, and `HostProviderName` must equal it unless a host is
exposed, so both take `ProviderName`'s value. `InvoiceDetailId` is the `InvoiceId`, section
5.3.

The first draft of this section, written the same day, said Meter normalised CUR 2.0 and
asked, as OPEN-21, whether to read the export instead, and it backfilled the service
provider from `PublisherName`. Reading the adapter showed the first premise wrong, and
FOCUS's definition of `ServiceProviderName` showed the second, CHG-0128.

### 5.3 Invoices come from the AWS Invoicing API

`ListInvoiceSummaries`, API version 2024-12-01, read from the payer through the credential
broker, with `invoicing:ListInvoiceSummaries` added to the reader role. It is read only,
constraint 6. A new collector, `invoices`, has its cadence row, daily, ADR-0012, its run in
the ledger, and the four typed causes. Only summary amounts exist, so an Invoice Detail row
is a whole invoice and its `InvoiceDetailId` is its `InvoiceId`. A credit memo is a row of
its own carrying its `OriginalInvoiceId`. The installed SDK, botocore 1.43.108, already has
the call, so nothing new is admitted.

### 5.4 The comparison

For each invoice, before tax: its `TotalAmountBeforeTax` against the sum of `billed_cost`
over rows with that `invoice_id` whose `charge_category` is not Tax. Tax: its
`Taxes.TotalAmount` against the rows whose `charge_category` is Tax. Both in the invoice's
currency; a row in another currency is a typed state, never converted silently.

| State | When |
| --- | --- |
| Matched | The difference is within the tolerance |
| Mismatched | It is not, and the difference is shown |
| Period open | The billing period has no issued invoice yet |
| No rows | An invoice names an id no cost row carries |
| Currency differs | The rows and the invoice are not in one currency |
| Not readable | The read failed: AccessDenied, Throttled, NotOptedIn or NoData |

The tolerance is 0.01 percent of the invoice's amount, modelled: rounding between line
items and an invoice is expected, and the figure is revisited once a real invoice has been
compared. It is a named constant with this reason beside it. A difference under one cent
always matches, added on 2026-10-08 with TASK-P10-004, CHG-0131: an invoice is stated in
cents, and without the floor a zero tax line would demand an exact match from a sum of rows
held to ten decimal places.

### 5.5 An invoice is payer wide

An invoice totals every account under the payer, so it is read only by a reader whose scope
covers the whole payer, the `PayerWide` rule, as budgets are by ADR-0025. A narrower reader
gets a typed refusal, never a total that includes accounts they cannot see.

## 6. Data model

Migration 0030, TASK-P10-002, adds to `cost_focus_daily`, all nullable at first:
`billing_account_name`, `billing_currency`, `charge_class`, `pricing_unit`,
`service_provider_name`, `host_provider_name`, `invoice_id`, `invoice_detail_id`. It
backfills both `service_provider_name` and `host_provider_name` from `provider_name`, and
holds `billing_currency` to three capital letters by a constraint. The
two old columns are dropped in a release after P10, never in it.

Migration 0031, TASK-P10-003, adds `billing_period` and `invoice_detail`, each with
`tenant_id`, the FOCUS 1.4 columns the API returns, `as_of` and `collected_at`, and their
invariants as constraints: the currency's format, a period that ends after it starts, an
amount that is never null on an issued invoice.

The comparison is computed when it is read, from the cost rows and the invoice rows, so it
cannot drift from either.

## 7. Interface

- `GET /api/v1/cost/reconciliation?period=YYYY-MM-DD`, an envelope of comparisons, exportable
  as every list route is.
- A screen, Invoice reconciliation, at `/report/reconciliation`.
- A tile on the FinOps practitioner's Overview, Matches the invoice, for the last period with
  an issued invoice, linking to the screen.
- The MCP server reaches it through the API, as it reaches every route, constraint 8.

## 8. Testing

- Each new column read from a fake export row where the table has it and null where it
  does not, the derived provider columns, and the backfill, with an old reader still
  reading after the migration.
- The invoice adapter with a stubbed client: pages, a credit memo, AccessDenied, throttling.
- The comparison in every state of section 5.4, the tax split, and a credit memo.
- A narrowed reader refused by type, never given a total.
- A journey through the screen and the tile.

## 9. Risks

- A sum of line items can differ from an invoice for reasons that are not errors: rounding,
  credits applied on the invoice, and Marketplace charges invoiced by another entity. Each
  invoicing entity's invoice is compared on its own.
- `ChargeClass` and the other columns are AWS's, and AWS documents gaps in its own
  conformance.
- For a Marketplace row, FOCUS 1.3 names the seller as the service provider, where an export
  older than 1.3 puts AWS in `ProviderName` and the seller in `PublisherName`. The derivation
  follows FOCUS's naming of the replaced column, so such a row says AWS until AWS exports a
  later version.
- No account is connected, so nothing here has met a real invoice.

## 10. Open questions

- OPEN-21, withdrawn on 2026-10-07: it asked whether to read AWS's FOCUS export, which
  Meter already reads, section 5.2.
- OPEN-08, already open: when a closed billing period is final.

## 11. Features delivered

FEAT-076, invoice reconciliation. FEAT-004 moves to FOCUS 1.4's mandatory columns.

## 12. Exit criteria

1. Every FOCUS 1.4 mandatory Cost and Usage column on Meter's row, held by a test that
   reads the list from this specification's section 4.
2. `ProviderName` carried into `ServiceProviderName` and `HostProviderName`, with an old
   reader still working.
3. Invoices read through a port with a fake and an AWS adapter, with typed failures and two
   timestamps.
4. Each invoice compared before tax and tax apart, in every state of section 5.4, never zero
   for a failure.
5. A narrowed reader refused by type.
6. The screen and the Overview tile, labelled measured.
7. `make verify` green, and the comparison against a real invoice recorded as waiting on
   ISS-002, ISS-003 and TASK-P9-001.
