# P1 Cost Intelligence: design specification

Status: draft, 2026-09-18.
Sub project: P1.
Depends on: P0, complete.
Supersedes nothing.

This specification covers the **cost surface** only. P1 as described in
`docs/01-ROADMAP.md` is larger, and section 3 names what this cut leaves out
and why.

## 1. Purpose

Meter today can tell you what your dashboards cost. It cannot tell you what
anything else costs, which makes it a query governance tool with a FinOps
platform's documentation.

This is the canonical cost surface: what was spent, by whom, on what, over
time. Every other sub project reads it. P3 cannot say a rightsizing
recommendation saves money without a bill to compare against. P5 cannot price
a quota increase. The FinOps Score has nothing to score. P2's own findings are
a projection until there is an invoice beside them, which is ISS-093.

It is also the first thing a person opens. The navigation shell has carried a
`Cost` group since ADR-0020 with five screens in it, every one of them
answering "arrives with P1 Cost Intelligence". This specification fills the
first two.

## 2. Definition of done

- `/cost` and `/cost/allocation` read live data for a seeded estate, and each
  has been opened and read rather than assumed to work.
- Ingest is idempotent under restatement. Running it twice on the same billing
  period leaves the same rows, and running it after AWS restates the period
  leaves the restated ones with nothing retracted still showing.
- Every figure carries `as_of` and `collected_at`, and every screen shows
  freshness, per constraints 4 and 10.
- An open billing period is labelled as open. A month in progress is never
  rendered as though it were a complete month.
- A failed account is typed and named, never rendered as zero, per constraint 5.
- Scope is enforced twice, and `cost_focus_daily` is in `SCOPED_TABLES` before
  a route reads it.
- `make verify` passes, which since 2026-09-06 means every backend test.

## 3. Out of scope

Named rather than left to be discovered, because the navigation group promises
five screens and this delivers two.

| Not in this cut | Why | Where it goes |
| --- | --- | --- |
| `/cost/anomalies`, FEAT-023 | An anomaly is a deviation from a baseline, and there is no baseline until the surface has been collecting for weeks. Building the detector first means tuning it against fabricated history | P1, second cut |
| `/cost/commitments`, FEAT-024 | Savings Plan and Reserved Instance utilization comes from a different API than CUR, and reads as a separate collector with a separate cadence | P1, second cut |
| `/cost/export`, FEAT-045 | The roadmap is right that finance is the actual consumer, and an export of a surface that is still changing shape is an export nobody can rely on | P1, second cut, and it should be soon |
| Cost Categories | An allocation input, and allocation works from tags first. Adding a second source before the first is proved makes a disagreement between them impossible to attribute | P1, second cut |
| Real CUR 2.0 through Athena | There is no AWS account. ISS-122 | Blocked, not descoped |

The AWS adapter is written in this cut and is not proved by it. It is unit
tested against recorded shapes and has never made a call. Saying so here is
cheaper than discovering it at a sign off.

## 4. Module structure

Layers per the import contract, which import-linter enforces:
`finops_mcp` > `finops_api` > `finops_ingest` > `finops_query` >
`finops_providers` > `finops_core`.

| Path | Action | What it is |
| --- | --- | --- |
| `finops_core/domain/cost.py` | extended | `CostRecord` exists. Add `BillingPeriod`, start inclusive and end exclusive, which answers `is_open` against a clock the caller passes, and `CostTotal`, which carries a `CostMeasure` and never a bare number. Openness is computed here rather than reported by the port, which keeps the adapter free of a clock |
| `finops_core/ports/cost.py` | **exists from P0, unchanged** | `CostExport`, with `latest_available_period()` and `read_period(start, end)`. Better than what this document first proposed: it separates an export that has published nothing from one that is missing, and it names `SchemaDrift`. ISS-180 |
| `finops_providers/fake/cur.py` | created | A synthetic estate in FOCUS shape with a configurable failure. `FakeProvider` already implements `CostExport` against a four row fixture, which is enough to prove the port and not enough to exercise a screen. ISS-180 |
| `finops_providers/aws/cur.py` | created | `AthenaCostExport`. Reads the Data Exports manifest, queries Athena, pages results. Unproved, see section 3 |
| `finops_ingest/collectors/cost_focus.py` | created | The collector. Normalizes to FOCUS 1.1, writes `cost_focus_daily`, derives `cost_focus_monthly` in the same transaction |
| `finops_api/db/repositories/cost.py` | created | `CostRepository`. Totals, by service, by account, by day, and the allocation split |
| `finops_api/guards.py` | edited | `cost_focus_daily` and `cost_focus_monthly` added to `SCOPED_TABLES` as `ByAccount` on `sub_account_id` |
| `finops_api/routes/cost.py` | created | Four routes, section 8 |
| `finops-web/src/screens/CostScreen.tsx` | created | `/cost`, spend and trend |
| `finops-web/src/screens/CostAllocationScreen.tsx` | created | `/cost/allocation` |
| `scripts/ops/seed_demo.py` | edited | The demo estate gains a bill |

`finops_query` is untouched. Cost does not pass through it.

## 5. Data model

**The tables already exist.** P0 migrated `cost_focus_daily` (partitioned by
`billing_period_start`), `cost_focus_monthly` and `cost_provider_extra` in
`0001_initial.py` and `0002_cost_monthly.py`. This cut writes to them and adds
no migration, which is the strongest evidence that the FOCUS decision in
constraint 2 was made early enough.

Three properties of that schema drive the design.

**`source_fingerprint` is the identity of a line item.** The primary key is
`(tenant_id, billing_period_start, source_fingerprint)`, so the fingerprint is
what makes an ingest idempotent. It is a hash of the columns that identify the
charge and not of the columns that state its size: billing account, sub
account, charge period start and end, service, resource id, sku, charge
category, and commitment discount id. Hashing the cost as well would make a
restated row a new row, which is the failure this key exists to prevent.

**`cost_focus_monthly` is derived, never ingested.** It is computed from daily
inside the same transaction that writes daily. Two sources for one number is
how the two come to disagree, and the disagreement is always found by a person
reading a screen rather than by a test.

**Partitions are created ahead of use.** `finops_ingest/collectors/partitions.py`
already does this and already refuses to write into a missing partition rather
than misfiling the cost. An ingest for a period with no partition fails, loudly,
and that is correct.

### Restatement, which is the whole problem

AWS restates the current month continuously and can restate a closed month.
A line item can change size, and a line item can disappear.

Changed is easy: the fingerprint is stable, the upsert replaces it.

Disappeared is not. If nothing deletes it, a charge AWS retracted stays on
Meter's bill forever and Meter's total drifts above the invoice by exactly the
amount of every correction ever issued. So:

1. Every row written by a run carries that run's `ingest_run_id`.
2. When a run has read **the whole period** successfully, it deletes the rows
   in that period whose `ingest_run_id` is not its own.
3. When a run failed part way, it deletes nothing.

Step 3 is the one that matters. A period half read looks exactly like a period
where half the charges were retracted, and a collector that cannot tell those
apart will delete a real bill the first time Athena throttles. This is
constraint 5 applied to a delete rather than to a number.

### Measures

`effective_cost` is the primary measure everywhere, which is amortized cost.
`billed_cost` is retained and shown only where the question is what the invoice
says. The roadmap made this decision and this specification does not reopen it.

Every total is a `CostTotal` carrying its measure, never a bare number. A
screen that renders amortized cost under a label saying billed is a defect
nobody can see, and typing it is the only thing that catches it.

## 6. Error taxonomy

The existing typed causes, unchanged: `AccessDenied`, `Throttled`,
`NotOptedIn`, `NoData`. Cost adds no new cause and needs none.

Two notes specific to this collector.

`NoData` for a billing period is a real answer and not an error. An account
that joined the organization last week has no charges in a period that closed
before it joined. It is reported as no data for that period, never as zero
spend, because zero spend is a claim and this is an absence.

`Throttled` from Athena is expected rather than exceptional. It is retried with
backoff by the adapter, and if it survives the retries the period is marked
incomplete and the delete in section 5 does not run.

## 7. Flow

```
Data Exports writes CUR 2.0 Parquet to S3, partitioned by billing period
        |
        v
AthenaCostExport                reads the manifest and says what the
  .latest_available_period()     export actually holds
        |
        v
AthenaCostExport                one Athena query per period, paged. Which
  .read_period(start, end)      periods to re read is the collector's policy,
        |                       because cadence is data, ADR-0012
        |
        v
cost_focus collector            normalizes each row to FOCUS 1.1,
        |                       computes source_fingerprint,
        |                       upserts cost_focus_daily
        v
        |                       on a complete period only:
        |                       delete rows whose ingest_run_id is not this run
        v
        |                       derive cost_focus_monthly for the period,
        |                       in the same transaction
        v
RunLedger                       claims, watermarks, records the outcome
```

The collector runs per billing period, not per account, because CUR is written
per payer and the whole organization arrives in one export. That is different
from every P0 and P2 collector, which run per account, and it is why the unit
for this collector carries a period rather than a scope key.

Cadence is data, per ADR-0012 and constraint 9. The open period is re read
several times a day because it is changing. A closed period is re read daily
for a week and then weekly, because a restatement can still arrive and the
cost of checking is one Athena query.

## 8. Interface

Four routes, all under `/api/v1/cost`, all returning the meta envelope.

| Route | Returns |
| --- | --- |
| `GET /cost/summary` | The current period's total, the previous period's total, and the change. Each a `CostTotal` with its measure and both timestamps |
| `GET /cost/by-service` | Services ranked by effective cost for a period, with the period's open or closed state |
| `GET /cost/by-account` | The same, by sub account, scoped |
| `GET /cost/trend` | Daily effective cost across the last n days, for the chart on `/cost` |

Allocation reads `by-account` and `by-service` with a tag key, rather than
adding a fifth route, because allocation is a grouping of the same rows and a
separate route would be a second implementation of one query.

Scope is enforced twice, per constraint 3. `cost_focus_daily` carries
`sub_account_id` directly, so the guard rule is `ByAccount` on that column, not
`Through` anything.

**A known trap, stated here because it has already cost this project six
defects.** TASK-P2-021 added routes over six tables that were not in
`SCOPED_TABLES`, and every one of them returned 500 on the first real call
while importing cleanly and passing its tests. The guard entry goes in before
the route, and the route is called before the task is called done.

## 9. User interface

Two screens, both in the existing `Cost` navigation group, replacing their
`arrives with P1` placeholders.

**`/cost`, Spend and trend.** The period total, the change against the previous
period, a daily trend, and the services that make it up. The open period is
labelled as open, beside the figure rather than in a footnote, because a reader
comparing a part month against a whole month with no warning will reach a wrong
conclusion confidently.

**`/cost/allocation`, Allocation.** Cost grouped by a tag key, with an explicit
`unallocated` row. The unallocated row is never hidden and never folded into a
total. An allocation view that quietly drops what it cannot attribute reports a
smaller estate than exists, and the gap between it and the invoice is the first
thing finance will find.

Both follow ADR-0021: plain CSS, and `layout.css` may not target a class a
component would have to add. Both use the warm severity ramp and IBM Plex
already in `tokens.css`. Every figure goes through `Figure`, which is what
carries provenance and freshness onto the screen.

## 10. Infrastructure

Terraform for the export bucket, the Glue catalog database and the Athena
workgroup, in the hub stack. It will pass `validate` and `fmt` and will not be
applied, because ISS-122. That is a statement of fact and not a plan.

No new IAM in a member account. CUR is read from the payer, which the hub role
already reaches.

## 11. Testing

The same shape P2 used, and the parts of it that were learned the hard way.

- Contract tests over the `CostExport` port, run against both the fake and the
  AWS adapter, so the fake cannot drift into agreeing with a matcher that does
  not exist.
- Restatement is tested directly: ingest a period, restate it with one row
  changed and one row removed, ingest again, assert the changed row changed and
  the removed row is gone.
- Partial failure is tested directly: fail the read part way and assert nothing
  was deleted.
- Every route is called. A test that imports a route proves nothing, which is
  the standing lesson in `tasks/lessons.md`.
- Integration tests run in the gate, since 2026-09-06.
- One Playwright journey: open `/cost`, read a figure, follow it to
  `/cost/allocation`.

## 12. Risks

| Risk | Why it matters | What reduces it |
| --- | --- | --- |
| The fake estate makes the surface look finished | P2 has ten screens working against fakes and nothing proved against AWS. A second sub project in the same state doubles the distance to the first real number | The fake is built to be obviously synthetic, and every screen says what it is reading |
| The delete in section 5 | It is the only destructive operation in the ingest path | It runs only on a complete period, and a test fails the read part way and asserts nothing was deleted |
| Athena cost | The tool that reports on cost can be expensive to run | One query per period per run, partition pruned. The platform meters itself, constraint 7, so this shows up on the front page like everything else |
| Scope on a wide table | `cost_focus_daily` is the widest table in the schema and the most damaging to leak | `ByAccount` on `sub_account_id`, the guard test, and the route called before it is called done |

## 13. Open questions

1. What does `/cost` show for a tenant whose first ingest has not run? An empty
   state, or the same "not built yet" panel the unbuilt screens use? They are
   different situations and should not look the same.
2. Should a closed period ever be re read after the restatement window, or is
   there a point at which Meter declares a month final and stops paying Athena
   to confirm it?
3. Does the unallocated bucket belong on `/cost` as well as `/cost/allocation`?
   It is the number most likely to embarrass an estate, which is an argument
   both ways.

## 14. Features delivered

| Feature | Name | In this cut |
| --- | --- | --- |
| FEAT-020 | CUR 2.0 ingest with resource identifiers and split cost allocation | Yes, against the fake. The AWS adapter is written and unproved |
| FEAT-021 | Cost rollups, trends and per resource attribution | Rollups and trends yes. Per resource attribution is stored and not yet on a screen |
| FEAT-022 | Allocation, showback and the unallocated bucket | Allocation and the unallocated bucket yes. Showback is the export, FEAT-045, and is not in this cut |
| FEAT-023 | Anomaly detection | No, section 3 |
| FEAT-024 | Savings Plan and Reserved Instance coverage | No, section 3 |
| FEAT-045 | Chargeback and showback export | No, section 3, and it should be the next thing |

## 15. Exit criteria

1. `make seed` produces an estate with a bill, and `/cost` shows it.
2. Ingesting the same period twice changes nothing, proved by a test that does
   it rather than by an argument that it would.
3. A restated period updates what changed and removes what was retracted.
4. A period that failed part way deletes nothing.
5. The open period is labelled open on screen.
6. The unallocated bucket is visible and is not folded into any total.
7. Scope is enforced twice, and a narrow scope sees less than a global one,
   proved by a test that calls the route with each.
8. `make verify` passes.
9. This document's open questions are answered or carried into the registry as
   open questions with an owner.

## 16. The second cut, and what changed about the decisions

Section 3 deferred three things with a reason each. This section records what
changed, because a deferral reversed without saying why is a deferral nobody
will trust next time.

**Anomalies, FEAT-023.** The reason stands: there is no baseline until the
surface has collected, and tuning a detector against fabricated history teaches
it the fixture. What changed is the shape of the answer. The detector refuses
rather than guesses, so a pair with fewer than fourteen days of history produces
no verdict at all. Its threshold is configuration rather than code, so meeting a
real estate is a change of a number and not a release. And it uses a median and
a median absolute deviation rather than a mean and a standard deviation, because
one spike inside a baseline window drags a mean far enough to hide the next
spike, which is the failure that matters for a detector nobody is watching.

Ingesting AWS Cost Anomaly Detection is still out. It is a second source with
its own port, it cannot be proved, and a screen showing two detectors that
disagree is worse than one that does not.

**Commitments, FEAT-024.** The reason stands and is why this is its own port and
its own collector rather than a widening of `CostExport`. A Savings Plan is not
a line item, and modelling it as one would put a second meaning on
`cost_focus_daily`.

Two numbers, never one. Utilization is how much of what you bought you used.
Coverage is how much of what you ran was bought in advance. A commitment can be
fully utilized and cover a tenth of the estate, and those are different
conversations with different actions, so a screen that reports one of them and
calls it commitment health is a screen that recommends the wrong thing half the
time.

**Export, FEAT-045.** The reason was that an export of a surface still changing
shape is one nobody can rely on. The surface stopped changing when TASK-P1-008
to TASK-P1-011 landed. The file is generated from the same repository the
screens read, so it cannot drift from what they show, and a test sums the file
and compares it against the summary route.

CSV only. Excel would mean admitting a dependency through `make dep-check` for a
format that spreadsheet software already opens, and the feature document says so
rather than leaving the gap to be discovered.

**Exit criteria for this cut.** The three remaining screens in the `Cost`
navigation group carry no "arrives with" note, every figure on them is scoped
twice and carries both timestamps, and the estate seeded by `make seed` contains
an anomaly the detector finds rather than one it was told about.
