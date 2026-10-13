# FEAT-089: Purchase plans, Meter's and AWS's side by side

| Field | Value |
| --- | --- |
| Sub project | P14 |
| Status | In build |
| Specification | [P14 spec](../specs/2026-10-13-p14-commitments-design.md), sections 5.1, 5.6 and 6 |
| Tasks | TASK-P14-006, TASK-P14-007 and TASK-P14-009 |
| Decisions | OPEN-35, OPEN-38 |
| Issues addressed | ISS-297, open |
| Refresh cadence | Daily |

## What it does

Drafts a purchase plan from the estate's own steady baseline and P9's Savings Plans rates under the tenant's policy, and shows it beside AWS's purchase recommendation with the difference in words.

## Why it exists

FEAT-055 turns an uncovered baseline into a finding priced at a configured percentage. A person deciding a purchase needs the rate the estate would actually get, the ladder it would fit, and a second opinion from the provider, each saying how it was arrived at.

## How it works

AWS's side is built, TASK-P14-006. The `purchase_recommendation` collector runs once a day as one organization wide unit. It reads the tenant's policy, then asks Cost Explorer, as the payer, for a recommendation for each Savings Plans type that covers EC2 (Compute and EC2 Instance) and for each service named by `METER_COMMITMENT_RECOMMENDATION_SERVICES`, every question in the policy's term and payment option over a 30 day lookback. `finops_providers/aws/commitment_recommendations.py` reads every page of a reservation answer. Each answer is one row of `purchase_recommendation`, keyed by tenant, kind and program, and a type or service no longer asked about leaves on the next run. An answer advising nothing is written as `recommended` false, because it is an answer.

The service names are Cost Explorer's own, and AWS documents only some of them. They are a setting so a name Cost Explorer refuses can be corrected without a release, and `make first-contact` asks for the first one as the payer, ISS-297.

Meter's own plan is not built yet, TASK-P14-007. `finops_query` will hold the arithmetic, pure: the tenth percentile of daily uncovered eligible on demand spend over 30 days, P9's rate for the families and Regions behind it, the policy's coverage less what is already held, and the ladder limit.

## Data sources and freshness

| Source | Cadence | Best possible freshness |
| --- | --- | --- |
| Meter's tables and P9's rates | Daily | The day before |
| Cost Explorer's recommendations | Daily | AWS's own refresh |

## Measured or modelled

Modelled: every figure in Meter's plan, with its inputs. AWS's estimated saving is AWS's, labelled so.

## Failure behaviour

A family with no P9 rate is unpriced and named, never priced at zero. A day the bill does not hold is not a day of zero. Each type and service is read on its own: one that fails is written as a row with its typed cause and no figures, beside those that answered, and shows that cause beside Meter's plan. Only a run where every read failed fails, and then the last good rows stay.

## Security considerations

Visible at global scope only. Each recommendation request costs USD 0.01, modelled, carried in the schedule row.

## Interface

`GET /v1/commitments/plans`, and the plans panel.

## Not doing

Choosing between the two plans, or buying either.
