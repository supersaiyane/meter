# FEAT-060: What somebody said this should cost

| Field | Value |
| --- | --- |
| Sub project | P1 |
| Status | Delivered |
| Specification | [competitive review](../11-COMPETITIVE-REVIEW.md), and the FinOpsForge dashboard checklist reviewed 2026-09-27 |
| Tasks | None. Adopted from review rather than planned |
| Refresh cadence | Daily, in `collector_schedule`, because a limit changes rarely and the spend it is compared against changes once a day |
| Source | Three independent reviews named the same absence |

## What it does

Reads the budgets an organization has already set at the provider, compares each one against the
spend Meter has collected for the same period, and says whether it is under, at risk, over, or
not computable.

## Why it exists

Three separate reviews arrived at the same gap. The IBM Turbonomic review has no budget in it
either, so it could not have suggested one. The FinOpsForge checklist puts budget against actual
at the top of the finance dashboard and a red amber green status at the top of the executive one.
And this product had no budget entity at all, which blocks budget against actual, a status light,
and forecast against budget, all three at once.

A cost figure on its own is not a finding. Eleven thousand dollars is either fine or a crisis, and
nothing in Meter knew which until now.

## How it works

`finops_core/domain/budget.py` holds the rule and is pure. `status_of` takes the limit, the
actual, and how far through the period we are, and returns one of four statuses. The margin that
separates at risk from under is configuration, `METER_BUDGET_AT_RISK_MARGIN`, defaulting to 0.1,
which is a modelled threshold and not a measured one.

**Collected, never entered.** The `budget` table carries `ingest_run_id` and both timestamps like
every other table here, because a budget read from a provider is a fact with a provenance. A
budget typed into Meter would be the first thing in the product with none, and it would need a
write API, a form, validation and an audit trail. That cost is real and is recorded as ISS-210.

**Nothing derived is stored.** Not the actual, not the status, not the percentage. The status
depends on where today falls in the period, so a stored one is wrong by the next morning, and a
stored actual would be a second copy of a number `cost_focus_daily` already holds. All three are
computed per request.

**Payer wide, per ADR-0025.** A budget is set at the payer and the API that reports it is a payer
API, so `finops_api/guards.py` scopes `budget` the way it scopes `commitment_coverage`. A narrowed
reader reads nothing rather than a figure that is not theirs. The cost of that is ISS-212.

## Failure behaviour

A budget whose scope Meter cannot reproduce, a tag expression for example, is stored with scope
`UNSUPPORTED` and is never matched to a number. It is counted and the count is reported on the
route, because a budget matched to the wrong spend is worse than a budget with no number.

A period with no collected cost yields `UNKNOWN`, not zero. Constraint 5: a failure is never
rendered as the number zero, and a budget compared against nothing is not a budget being
underspent.

Non monthly and non cost budgets are read and marked `UNSUPPORTED` rather than dropped, so the
count on the screen is the count the provider holds.

## Security considerations

Read only, and no write path exists. Constraint 6. No limit can be set or changed through Meter.

## Interface

`/cost/budgets`, and one tile on the home screen.

The card draws a bar whose fill is the fraction spent and whose vertical tick is the fraction of
the period elapsed. That is the whole design: ninety five percent spent is healthy on the twenty
eighth and alarming on the fourth, so a progress bar alone carries no finding. The gap between the
fill and the tick is what a reader is looking for, and it is the same arithmetic the server does
to produce the status, drawn rather than described, so a reader can disagree with the light.

`components/BudgetBar.tsx` is shared by both surfaces on purpose. A fill computed one way on the
home tile and another way on the screen would be two pictures of one fact.

Budgets with no number are listed separately with a count and with the reason on each card. A
screen showing two statuses above ten blanks is saying something false about the estate. The two
reasons are kept apart because they need different actions: an unsupported scope is never fixed
by waiting, and an uncollected period is.

The home tile shows the budget running furthest ahead of its calendar, not the largest limit and
not the most spent. Budgets do not add up: four healthy ones and one blown one average to fine,
and the blown one is the news.

## Not doing

Setting a budget, forecasting against one, and alerting on one. The provider already alerts on
every limit here, and a second alerting path would double somebody's notifications while
disagreeing with the first about when to fire.
