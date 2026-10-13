# FEAT-089: Purchase plans, Meter's and AWS's side by side

| Field | Value |
| --- | --- |
| Sub project | P14 |
| Status | Specified |
| Specification | [P14 spec](../specs/2026-10-13-p14-commitments-design.md), sections 5.1, 5.6 and 6 |
| Tasks | TASK-P14-006, TASK-P14-007 and TASK-P14-009 |
| Decisions | OPEN-35, OPEN-38 |
| Issues addressed | None yet |
| Refresh cadence | Daily |

## What it does

Drafts a purchase plan from the estate's own steady baseline and P9's Savings Plans rates under the tenant's policy, and shows it beside AWS's purchase recommendation with the difference in words.

## Why it exists

FEAT-055 turns an uncovered baseline into a finding priced at a configured percentage. A person deciding a purchase needs the rate the estate would actually get, the ladder it would fit, and a second opinion from the provider, each saying how it was arrived at.

## How it works

Not built yet. `finops_query` holds the arithmetic, pure: the tenth percentile of daily uncovered eligible on demand spend over 30 days, P9's rate for the families and Regions behind it, the policy's coverage less what is already held, and the ladder limit. The `purchase_recommendation` collector reads AWS's two recommendation calls as the payer.

## Data sources and freshness

| Source | Cadence | Best possible freshness |
| --- | --- | --- |
| Meter's tables and P9's rates | Daily | The day before |
| Cost Explorer's recommendations | Daily | AWS's own refresh |

## Measured or modelled

Modelled: every figure in Meter's plan, with its inputs. AWS's estimated saving is AWS's, labelled so.

## Failure behaviour

A family with no P9 rate is unpriced and named, never priced at zero. A day the bill does not hold is not a day of zero. A failed recommendation read shows its cause beside Meter's plan.

## Security considerations

Visible at global scope only. Each recommendation request costs USD 0.01, modelled, carried in the schedule row.

## Interface

`GET /v1/commitments/plans`, and the plans panel.

## Not doing

Choosing between the two plans, or buying either.
