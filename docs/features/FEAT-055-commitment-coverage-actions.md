# FEAT-055: A commitment coverage gap as a ranked action

| Field | Value |
| --- | --- |
| Sub project | P1 |
| Status | Specified |
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

Reads the commitment coverage FEAT-019 collects and emits a recommendation for a baseline of
usage that was uncovered across the observation window. The rationale publishes the term, the
break even month and the window it was computed from.

## Failure behaviour

Usage below the observation minimum produces no finding, on the same principle as FEAT-054.

The saving is modelled and never measured. Realized saving is measured afterwards by FEAT-041,
which is the only thing in the product allowed to say a saving happened.

## Security considerations

Read only, and no purchase path exists. Constraint 6. The coverage read is already scoped.

## Interface

`/waste`, with the rest. The commitments screen is unchanged: this adds a consumer rather than
a second view.

The risk verdict is the least reversible in the product. A commitment cannot be handed back,
so this is permanent and it says so.

## Not doing

Buying anything, and naming a specific Savings Plan product. The finding says a baseline is
uncovered and what covering it would be worth. Which instrument to use is a procurement
decision with constraints we do not hold, and a tool that picked one would be wrong in a way
nobody could see until the term ended.
