# FEAT-087: The effective savings rate as the headline, measured from the bill

| Field | Value |
| --- | --- |
| Sub project | P14 |
| Status | In build |
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

Built: the API, TASK-P14-004, and the screen, TASK-P14-009. `CostRepository.savings_rate_months`
sums, per billing month, Effective Cost and List Cost over the cloud bill's usage lines that carry a
List Cost, and counts the lines that carry none with what they cost. `finops_query/savings_rate.py`
makes the rate, one minus Effective over List Cost, to a hundredth of a percent; a month whose lines
carry no List Cost has no rate and the reason, and usage dearer than list is a rate below zero rather
than one hidden. `GET /v1/commitments/savings-rate?months=12` returns the months oldest first,
exportable, scoped as the bill is.

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

`GET /v1/commitments/savings-rate`, and the headline of the commitments screen, built in TASK-P14-009: the newest month's rate, or the API's reason where it has none, and every month with both sums. The Overview's savings rate tile reads the same route by the same twelve months, so the two screens share one answer and cannot disagree.

## Not doing

A rate modelled from list prices Meter looks up itself; the bill's List Cost is the denominator.
