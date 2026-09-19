# FEAT-021: Cost rollups, trends and per resource attribution

| Field | Value |
| --- | --- |
| Sub project | P1 |
| Status | In build |
| Specification | [P1 spec](../specs/2026-09-18-p1-cost-intelligence-design.md) |
| Tasks | [P1 plan](../plans/P1-implementation-plan.md), TASK-P1-006, TASK-P1-008 to TASK-P1-010 |
| Screen | `/cost` |

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

## Not doing

Per resource attribution has a column and no screen. The rows are stored and who
should see them is a separate decision.

## Honestly

The open period label is the load bearing part of this screen. A month in
progress holds fewer days than the one before it, so its total is lower, and a
reader comparing them unwarned concludes spending collapsed. Everything else
here is arithmetic.
