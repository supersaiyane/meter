# FEAT-062: What Meter looked at and decided not to recommend

| Field | Value |
| --- | --- |
| Sub project | P3 |
| Status | Planned |
| Specification | [ADR-0027](../adr/ADR-0027-no-performance-dimension-in-p5.md) |
| Tasks | None yet |
| Source | The argument FEAT-058 asked for, held on 2026-09-28 |

## What it does

Shows the resources Meter examined and declined to recommend anything about, with the
measurement that decided it.

## Why it exists

The competitive review's sharpest line is that "a tool that only ever recommends making
things smaller is one engineers learn to discount". ADR-0027 argues that the remedy for
that is not to start recommending growth, which this product cannot verify and has no
service level input for, but to show that the tool looked.

An engineer whose service never appears in a waste list cannot tell whether it was
examined and found correctly sized, or never examined at all. Those are very different
facts and the product currently renders them identically, which is the same defect as
rendering a collection failure as the number zero.

## How it works

Nothing new is computed. `finops_query/waste.py` already produces the judgement:
`_refused` returns an `Estimate` carrying a reason, and the reasons are already written
for a reader.

`finops_ingest/collectors/waste_compute.py` ends `_judge` with
`return smaller if smaller.is_worth_acting_on else None`, which discards it. The work is
to keep it.

**A refusal is not a recommendation and must not be stored as one.** It has no saving,
so writing it into `recommendation` would put rows with a zero saving into a table whose
every consumer ranks by money, and ADR-0016 orders that list by exactly that figure. A
zero there reads as the least valuable action rather than as the absence of one, which
is the defect the taxonomy exists to prevent wearing a different hat. Its own table,
following ADR-0025's reasoning about a finding inheriting the shape of what it is.

## Failure behaviour

A resource with no judgement at all is different again from one that was refused, and
both are different from one with a finding. The screen has to keep three states apart:
recommended, examined and declined, and not examined. Collapsing the last two is the
whole defect this feature exists to fix, so doing it here would be self defeating.

A refusal is only as good as its reason. A reason that says "did not qualify" would be
worse than no feature, because it would teach a reader that the explanations are empty.

## Security considerations

Read only, and scoped like every other read. A refusal names a resource, so it is
account scoped by the same guard as the inventory.

## Interface

Beside the waste list rather than inside it, because a refusal ranked among findings
would need a severity and it has no money to derive one from. ADR-0016 survives
untouched precisely because this is a different surface.

## Not doing

Saying a resource is correctly sized. Meter can say it found no reason to shrink this
one against the measurements it took, which is a smaller and true claim. Correctly sized
is a statement about a service level that ADR-0027 says the product cannot see.
