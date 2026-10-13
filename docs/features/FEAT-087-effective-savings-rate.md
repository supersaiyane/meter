# FEAT-087: The effective savings rate as the headline, measured from the bill

| Field | Value |
| --- | --- |
| Sub project | P14 |
| Status | Specified |
| Specification | [P14 spec](../specs/2026-10-13-p14-commitments-design.md), sections 5.7 and 8 |
| Tasks | TASK-P14-004 and TASK-P14-009 |
| Decisions | None |
| Issues addressed | None yet |
| Refresh cadence | Reads what the cost collector wrote |

## What it does

Puts the effective savings rate at the top of the commitments screen: one minus Effective Cost over List Cost, by month, with both sums beside it.

## Why it exists

Utilization and coverage say how well a commitment is used and how much is covered. Neither says what the discounts saved, which is the figure a finance reader asks for first and the one the vendors lead with.

## How it works

Not built yet. A query over `cost_focus_daily` sums Effective Cost and List Cost by billing month on every line that carries a List Cost, and counts the lines that carry none.

## Data sources and freshness

| Source | Cadence | Best possible freshness |
| --- | --- | --- |
| The bill | As the cost collector runs | The bill's own lag |

## Measured or modelled

Measured: both sums are the bill's.

## Failure behaviour

A month whose lines carry no List Cost shows no rate and says why, never a rate of zero.

## Security considerations

Scoped by account as the bill is; a narrowed reader sees the rate of their accounts.

## Interface

`GET /v1/commitments/savings-rate`, and the headline of the commitments screen.

## Not doing

A rate modelled from list prices Meter looks up itself; the bill's List Cost is the denominator.
