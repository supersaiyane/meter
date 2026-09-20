# FEAT-029: Realized savings verification

| Field | Value |
| --- | --- |
| Sub project | P3 |
| Status | Specified |
| Specification | [P3 spec](../specs/2026-09-20-p3-utilization-and-rightsizing-design.md), section 5.5 |
| Tasks | TASK-P3-013, TASK-P3-014, TASK-P3-018 |
| Refresh cadence | Monthly, 60 day lag |

## What it does

Measures what actually appeared in the bill 60 days after a recommendation was marked done, verified against CUR.

## Why it exists

ISS-029. This is the north star metric. Identified savings is a vanity number that every FinOps tool inflates.

## What is already known

Compares the affected resource's amortized cost before and after, controlling for usage change, and marks a recommendation regressed if the saving did not persist.

## How it works

Sixty days after a recommendation is marked `DONE`, the affected resource's cost is
read from `cost_focus_daily` over matched windows: 30 days before, and 30 days
ending 60 days after.

**What this can claim, and what it cannot**, is the whole feature. A resource that
cost 100 dollars before and 60 after did not necessarily save 40. It may have been
used less. The honest counterfactual, what it would have cost had nothing changed,
is unobservable, and a tool claiming to know it is modelling and calling it
measurement.

So the claim is exactly: the amortized cost fell by this much, and the usage
quantity moved by this much over the same window. Both are shown.

## Failure behaviour

Three verdicts, not two. Where usage fell by more than cost did, the verdict is
`INCONCLUSIVE`, because the saving cannot be told apart from a workload that shrank
on its own. Where the saving did not persist, `REGRESSED`.

**`INCONCLUSIVE` is expected to be common, and is listed rather than hidden.** A
north star metric that is only ever green is the vanity metric ISS-029 warns about,
and the inconclusive verdicts are the evidence this one is not.

## Security considerations

Reads the cost tables under their existing guard. Adds no new access.

## Interface

`GET /waste/savings` and `/waste/savings`, which is the one screen in this product
where a number is allowed to be disappointing. Realized against estimated, and the
gap is the point.

## Not doing

**Adding realized and estimated savings together, ever.** They are different kinds
of number, live in different tables, are returned by different routes, and a test
exists whose only job is to try the sum and fail. Every tool inflates identified
savings, and the inflation always happens by quietly adding a modelled number to a
measured one.
