# FEAT-089: Purchase plans, Meter's and AWS's side by side

| Field | Value |
| --- | --- |
| Sub project | P14 |
| Status | In build |
| Specification | [P14 spec](../specs/2026-10-13-p14-commitments-design.md), sections 5.1, 5.6 and 6 |
| Tasks | TASK-P14-006, TASK-P14-007 and TASK-P14-009 |
| Decisions | OPEN-35, OPEN-38, OPEN-40 |
| Issues addressed | ISS-297, open |
| Refresh cadence | Daily |

## What it does

Drafts a purchase plan from the estate's own steady baseline and P9's Savings Plans rates under the tenant's policy, and shows it beside AWS's purchase recommendation with the difference in words.

## Why it exists

FEAT-055 turns an uncovered baseline into a finding priced at a configured percentage. A person deciding a purchase needs the rate the estate would actually get, the ladder it would fit, and a second opinion from the provider, each saying how it was arrived at.

## How it works

AWS's side is built, TASK-P14-006. The `purchase_recommendation` collector runs once a day as one organization wide unit. It reads the tenant's policy, then asks Cost Explorer, as the payer, for a recommendation for each Savings Plans type that covers EC2 (Compute and EC2 Instance) and for each service named by `METER_COMMITMENT_RECOMMENDATION_SERVICES`, every question in the policy's term and payment option over a 30 day lookback. `finops_providers/aws/commitment_recommendations.py` reads every page of a reservation answer. Each answer is one row of `purchase_recommendation`, keyed by tenant, kind and program, and a type or service no longer asked about leaves on the next run. An answer advising nothing is written as `recommended` false, because it is an answer.

The service names are Cost Explorer's own, and AWS documents only some of them. They are a setting so a name Cost Explorer refuses can be corrected without a release, and `make first-contact` asks for the first one as the payer, ISS-297.

Meter's own plan is built, TASK-P14-007. The `purchase_plan` collector runs once a day as one organization wide unit and reads only Meter's tables: the last 30 days of the bill's EC2 instance hours on demand, at their on demand equivalent, P9's on demand price and its two Savings Plans rates for each usage type in the policy's term and payment option, and what the inventory holds for EC2. `finops_query/purchase_plan.py` holds the arithmetic, pure, spec section 5.6:

- The steady baseline is the tenth percentile of the daily spend over the days the bill holds, divided by 24; a day the bill does not hold is left out, and fewer than 14 days draft a plan that says so and buys nothing.
- Split by stability, OPEN-40: each family steady in a Region buys an EC2 Instance Savings Plan, and steady usage that moves between families buys a Compute Savings Plan. A share with no rate is named as unpriced, never priced at zero.
- The target is the policy's coverage of that baseline less what is held past the month, each held commitment landing on the family it is bound to or, if flexible, anywhere.
- The ladder: at most the policy's limit of the organization's hourly commitment, held and planned, ends in any month, given what already ends then. This month's tranche is bought and up to eleven later ones are named; what twelve cannot place is reported.

There is one plan per month. It is redrafted daily while it is a draft, a draft nobody approved in its month lapses, and a plan somebody acted on is left as it is. The database refuses a transition out of order. `GET /v1/commitments/plans` returns the newest plan, its lines, the unpriced shares, AWS's recommendations and the difference in words.

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

`GET /v1/commitments/plans`, built: the newest plan, its lines as the rows of a file export, the unpriced shares, AWS's recommendations, and the difference in words. Global scope only. The plans panel, TASK-P14-009, shows Meter's plan by tranche beside AWS's recommendations, the difference as sentences, and each unpriced share named.

## Not doing

Choosing between the two plans, or buying either.
