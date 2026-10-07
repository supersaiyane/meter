# FEAT-065: Cost Explorer, two group bys over FOCUS dimensions and tags

| Field | Value |
| --- | --- |
| Sub project | P8 |
| Status | Delivered |
| Specification | [P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), sections 5.3 and 7 |
| Tasks | TASK-P8-007 |
| Screen | `/analyze/explorer` |

## What it does

`GET /cost/explore` and its screen answer the question a practitioner asks first, with the rows
the product already holds. A person groups cost two ways at once, over eight FOCUS columns and
the tag keys on the period's own line items, filters it, and reads it daily or monthly over month
to date, 3, 6 or 12 months, year to date or a custom period, set against the period immediately
before it. Effective Cost is the default, and Billed, List and Contracted Cost are offered only
where every line item in the view carries them.

## Why it exists

The owner said on 2026-10-05 that there is no graphical dashboard or report a person can take
away, and the audit the same day found no chart library and no screen called a report or a
dashboard. Today's Spend and trend screen becomes Cost Explorer under Analyze, named for the
Framework's Reporting and Analytics capability and for AWS Cost Explorer.

## What is already known

It sits behind the same scope dependency and repository guard as `/cost`, carries coverage and
failures in the envelope, and shows unallocated cost rather than hiding it. The query is bounded,
with partition pruning on the period and a row limit the answer names. No figure is computed
differently: it reads rows the API already holds, and its Excel and CSV export is FEAT-067's.

## How it works

The owner chose four things on 2026-10-05, each the recommended option.

| Choice | Chosen |
| --- | --- |
| Layout | Three tiles, this period, the period before and the change; a stacked column chart over time split by the first grouping; one sortable, totalled table of both groupings |
| Groupings | Service, Service category, Sub account, Region, Availability zone, Charge category, Commitment discount type and Commitment discount status, and tag keys |
| Tag keys | The 50 most used on the period's line items, so nothing needs keeping |
| Comparison | Like for like: month to date 1 to 5 October against 1 to 5 September, three months against the three before, a custom range against as many days just before it |

The period arithmetic is pure, in `finops_core/domain/explore.py`, and tested against fixed
dates, because a boundary tested on whatever day the suite runs is tested on one day in thirty.
The reads are in `finops_api/db/repositories/explore.py`, and every one is derived from
`scoped_select`, the only constructor the scope guard accepts. Wrapping a query in another would
drop the guard's mark, so the ranking is a window count over the grouped rows and the tag keys
are a function joined in the FROM clause. Each window bounds `billing_period_start` first, the
partition key, so the planner reads only the months the window touches, then
`charge_period_start` for the exact days. A grouping value that is missing becomes the
unallocated bucket, as the cost screen always did.

The table holds at most 500 rows. The answer says how many it left out and what they add up to,
the screen draws that as one more row, and so the rows always reconcile to the totals. Every row
naming the unallocated bucket is read separately, so the limit can never be what drops it. The
chart names the largest five groups, unallocated always among them, and folds the rest into one
series, which keeps it to the six series colours.

The screen keeps the whole view in the address under the route's own parameter names, so a link
lands on the view it was copied from and the screen hands its query string to the route
unchanged. Every value in the table links to the same view filtered to it, each filter is a chip
that takes itself away, and the controls sit outside the state boundary, so a view that answers
with nothing can still be changed into one that answers.

## Failure behaviour

- A tenant with no cost at all is answered 404, never zero.
- A view that cannot be drawn is refused with 422 and the sentence that says why: one grouping
  twice, a column or tag key outside the allow list, half a tag filter, a custom period without
  both dates, ending after today or longer than 366 days, or a measure some line item lacks.
- A previous window that starts before the first month Meter holds is not compared. Its figures
  are null, never zero, and the screen says so.
- A window that starts before the first month Meter holds says where the line items start.
- A window that ends today says it is still open, from the server's clock.
- A window with nothing billed yet, the first of a month, keeps the newest period's coverage and
  freshness rather than reporting an estate of nothing.

## Security considerations

Scope is enforced in both places, the request dependency and the repository guard. A grouping or
filter column is looked up in `EXPLORABLE`, never interpolated. A tag key is accepted only from
the allow list and travels as a bound value into the JSONB lookup. A filter holds at most 20
values of at most 256 characters, and a name at most 128, so a request cannot hand the database
an unbounded list. No refusal echoes what the request sent.

## Interface

`GET /api/v1/cost/explore` takes `group_by` and `then_by`, each a column or `tag` with
`group_by_tag` or `then_by_tag`; `period` (`mtd`, `3m`, `6m`, `12m`, `ytd`, `custom`) with
`start` and `end` for a custom one; `granularity` (`daily`, `monthly`); `metric`
(`effective_cost`, `billed_cost`, `list_cost`, `contracted_cost`); one repeatable filter per
grouping column; and `tag_key` with a repeatable `tag_value`. The answer, `ExploreOut` in
`finops_api/schemas.py`, carries both windows, whether the window is still open, the first month
held, the allow list of tag keys, both totals, the chart's named series and points, the rows,
and the row limit with what it left out.

## Not doing

- Months older than the 37 months of line items Meter keeps, which survive only as a monthly
  aggregate by account, service and region.
- Resource as a grouping. Its values run to tens of thousands, and the table would be mostly
  what the limit left out.
- More than one tag filter at a time.
- Exporting a view to Excel or CSV, which is FEAT-067, and saving one, which is FEAT-068.

## Status of this document

Delivered on 2026-10-05 by TASK-P8-007. The spend and trend screen at `/analyze/explorer` became
this one, and FEAT-021's routes still serve the Overview and the assistant.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P8.
