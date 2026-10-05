# FEAT-021: Cost rollups, trends and per resource attribution

| Field | Value |
| --- | --- |
| Sub project | P1 |
| Status | In build |
| Specification | [P1 spec](../specs/2026-09-18-p1-cost-intelligence-design.md) |
| Tasks | [P1 plan](../plans/P1-implementation-plan.md), TASK-P1-006, TASK-P1-008 to TASK-P1-010 |
| Screen | `/`, the Overview's spend tile. `/analyze/explorer` is FEAT-065's since 2026-10-05 |

## What it does

Answers what the estate spent this period, how that compares with the period
before, which services it went on, and how it moved day by day.

## Why it exists

It is the first screen a person opens, and the number every conversation about
cost starts from.

## How it works

`cost_focus_monthly` is derived from `cost_focus_daily` by one function with two
callers, so the two grains cannot disagree. Four routes read through
`CostRepository`, which cannot express an unscoped query. Every grouping is
asserted to sum back to the period total, because a grouping that does not is
dropping rows and reads on screen as a smaller estate.

## What is already known

Amortized cost throughout. Billed cost travels beside it so a reconciliation has
something to reconcile with, as separate columns rather than one column with a
mode.

## Failure behaviour

A tenant with no cost gets a 404, never a zero, because zero spend is a claim and
an uncollected estate is an absence. No earlier period gives a null change rather
than no movement. A collection failure reaches the trust strip through the
envelope.

## Security considerations

Scope enforced twice: the route's dependency and the repository guard. A narrow
scope is served strictly less than a global one, proved through the client. Every
read writes an `audit_event` in the same transaction.

## Interface

`GET /cost/summary`, `/cost/by-service`, `/cost/by-account`, `/cost/trend`. All
return the meta envelope, and the summary says whether the period is still open.

Two charts were added to `/cost` on 2026-09-27, and one of them replaced an instrument that was
wrong for the screen. The trend was a sparkline, and a sparkline by its own definition answers
whether something is going up and refuses to be read off. This is the screen somebody opens in
order to read the trend off it, so it draws the bar chart instead, which has a scale and a
labelled peak. The sparkline is still right where it was chosen for that property, on the platform
screen's per module rows.

The service breakdown is now a ranked bar above the table. This is the most opened screen in the
product and its breakdown was a column of numbers: which services the spend is on is a comparison,
and a comparison read off a column is arithmetic a reader should not have to do. Share of the
period's total, so the first few bars add up by eye to most of the bill.

The chart and the table are the same rows and are held to the same order by a test. A reader who
catches those two disagreeing about which service is largest stops trusting both.

On 2026-10-05 TASK-P8-007 replaced this screen with Cost Explorer, FEAT-065, which reads
`/cost/explore` and draws the same line items grouped two ways. The routes here still serve the
Overview's spend tile and trend, the assistant's cost answers and the export. The history above
is the spend and trend screen's, kept because three of its decisions carried over: the open
period is said, unallocated is never hidden, and a figure is set against the period before only
where that period was collected.

The screen was given a hierarchy on 2026-09-27. Its headline figure was rendering at body size,
so the most opened screen in the product showed the number it exists for as a line of prose while
the summary of it on the front page showed the same number at forty pixels. The figure and the
chart of that figure are now one panel rather than two, because two panels say they are two
things, and each panel says what it is: a block that renders a figure, then a chart, then a table
with nothing naming any of them is readable to whoever built it and a guessing game for everybody
else.

The trend's range line ran on: two dates, two figures and two freshness phrases in one paragraph,
six facts and no structure. It is split to the ends of the chart it describes, like the chart's
own axis.

## Not doing

Per resource attribution has a column and no screen. The rows are stored and who
should see them is a separate decision.

## Honestly

The open period label is the load bearing part of this screen. A month in
progress holds fewer days than the one before it, so its total is lower, and a
reader comparing them unwarned concludes spending collapsed. Everything else
here is arithmetic.
