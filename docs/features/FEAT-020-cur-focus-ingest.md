# FEAT-020: CUR 2.0 and FOCUS ingest

| Field | Value |
| --- | --- |
| Sub project | P1 |
| Status | In build |
| Specification | [P1 spec](../specs/2026-09-18-p1-cost-intelligence-design.md) |
| Tasks | [P1 plan](../plans/P1-implementation-plan.md), TASK-P1-001 to TASK-P1-007 |
| Refresh cadence | 6 hours, as a row in `collector_schedule` with its reason |

## What it does

Reads a billing export, one period at a time, and writes it to `cost_focus_daily`
in FOCUS 1.1. Corrects what the provider restated and removes what it withdrew.

## Why it exists

Every other sub project reads this table. P3 cannot claim a rightsizing
recommendation saves money without a bill to compare against, P5 cannot price a
quota, and P2's own findings stay projections until an invoice sits beside them.

## How it works

`CostExport` has two methods: which period the export holds, and the rows for a
period. `AthenaCostExport` runs one partition pruned query per period.
`FakeCostExport` answers from a synthetic estate. The collector computes nothing
about identity itself: `source_fingerprint` in `finops_core.domain.cost` is one
function both adapters call, hashing the columns that identify a charge and
never the columns that state its size.

A period is upserted, then rows this run did not see are removed, then the month
is rolled up. All three in the transaction the worker opened, so the daily table
and the monthly one are never briefly in disagreement.

## What is already known

Parquet and partitioned, read through Athena for extract only and never in the
serving path. Amortized cost is the primary measure, billed cost is retained for
reconciliation. Cadence is a row, per ADR-0012.

## Failure behaviour

Typed, never a zero. A throttled read is retried with backoff and then raises
rather than returning a short period, because a period read half way is
indistinguishable from a period half withdrawn and the removal turns on exactly
that difference. A missing partition is refused by the database rather than
worked around, per constraint 11. An export that exists and has published
nothing is `NoData`, which is a different answer from an export that is missing.

## Security considerations

Read only, per constraint 6. The export is read from the payer with the hub's
own credentials, so no member account IAM is involved. Nothing here is reachable
without a scope: the tables it writes are scoped `ByAccount` on
`sub_account_id`, corrected under ISS-184.

## Interface

No HTTP surface of its own. It writes the tables FEAT-021 and FEAT-022 read.

## Not doing

Cost Categories, which are a second allocation source and would make a
disagreement with tags impossible to attribute. Streaming a period, which cannot
be made safe until the port can say whether a read finished, ISS-181. Re reading
closed periods, ISS-183.

## Honestly

**`AthenaCostExport` has never made a call.** It is written against the
documentation, unit tested against recorded shapes and held to the same contract
as the fake. None of that is the same as having run, and the column mapping is
the part only a real export can settle. ISS-122.
