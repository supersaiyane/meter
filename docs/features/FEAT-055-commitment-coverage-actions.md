# FEAT-055: A commitment coverage gap as a ranked action

| Field | Value |
| --- | --- |
| Sub project | P1 |
| Status | Delivered |
| Specification | [competitive review](../11-COMPETITIVE-REVIEW.md), 2026-09-26 candidate list |
| Tasks | `TASK-P1-022` |
| Refresh cadence | Follows FEAT-019, the commitment collector |
| Source | Adopted from the IBM Turbonomic review on 2026-09-26 |

## What it does

Turns the commitment coverage we already report into recommendations with a money figure, an
owner and a lifecycle, so an uncovered steady baseline arrives in the same list as every other
finding.

## Why it exists

We report coverage and nobody owns it. A percentage on a chart is a fact; a recommendation has
an owner, a lifecycle and a realized saving measured afterwards, which is machinery P3 built
and nothing in P1 uses. A chart is read once a quarter. A finding is worked.

## How it works

Reads the commitment coverage FEAT-019 collects and writes a finding per uncovered dimension.
`finops_query/commitment.py` holds the arithmetic and is pure.

**Two deviations from the plan, both stated rather than quietly made.**

`commitment_action`, its own table, not rows in `recommendation`. ADR-0025 is the argument: a
commitment is bought at the payer and its coverage cannot be apportioned, which is why
`commitment_coverage` is `PayerWide`. A finding derived from a payer wide fact is payer wide, and
`recommendation` is scoped by account, so writing these rows into it would have meant stamping an
account on a payer wide figure and disclosing the organization's commitment position to whoever
held that account. A finding inherits the scoping of the fact it was computed from.

**The usage floor, not a break even month.** The plan asked for the break even month. For a no
upfront commitment billed monthly that is one, always, on every row, because the discount applies
from the first invoice. A number that is the same on every finding is not evidence, and
publishing it would have satisfied the criterion while telling a reader nothing.

The honest figure is the one that decides whether the purchase was a mistake: at a discount of
d, the commitment beats on demand while usage stays above `1 - d` of today's, and below that the
unused commitment costs more than the discount saved. A thirty percent discount means usage may
fall by thirty percent before the decision goes negative, which is a sentence somebody can hold a
capacity plan against.

## Failure behaviour

Usage below the observation minimum produces no finding, on the same principle as FEAT-054.

The saving is modelled and never measured. Realized saving is measured afterwards by FEAT-029,
which is the only thing in the product allowed to say a saving happened.

## Security considerations

Read only, and no purchase path exists. Constraint 6. The coverage read is already scoped.

## Interface

`/cost/commitments`, under the coverage table it derives from, rather than `/waste`. The findings
are payer wide and `/waste` is a per account list, so putting them there would have needed the
scoping exception ADR-0025 refused. The coverage table answers how much is uncovered and the
section under it answers what to do about it, which is the difference between a fact nobody owns
and a decision somebody works.

The risk label comes from the same module the waste screen and the home panel use, so a reader is
not told a change is permanent in one place and reversible in another. A commitment is the least
reversible finding in the product: nothing stops to buy one, which is exactly why it reads as
safe.

## Not doing

Buying anything, and naming a specific Savings Plan product. The finding says a baseline is
uncovered and what covering it would be worth. Which instrument to use is a procurement
decision with constraints we do not hold, and a tool that picked one would be wrong in a way
nobody could see until the term ended.
