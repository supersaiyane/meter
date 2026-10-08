# FEAT-078: The savings ledger, verified savings credited and re-measured

| Field | Value |
| --- | --- |
| Sub project | P11 |
| Status | Planned |
| Specification | [P11 spec](../specs/2026-10-08-p11-owners-and-savings-ledger-design.md), sections 5.5 and 5.6 |
| Tasks | TASK-P11-006 to TASK-P11-008 |

## What it does

Credits each saving FEAT-029 verifies to the recommendation's owner when it was marked done, the
team that owner's resource names, and whoever closed it. Every month afterwards it measures
whether the bill still shows the saving: a month that held adds what it saved, a month that
regressed stops the credit and says so, and a month with no cost for the resource is unobserved,
never a zero. A ledger screen ranks teams by the savings they hold, labelled measured.

## Why it exists

The State of FinOps 2026 survey names "once you fix it, it's gone" as the unsolved problem:
engineers get no lasting credit for savings they make (as reported by the survey). Meter already
verifies a saving against the bill once, FEAT-029, and credits it to nobody.

## What is already known

Only a VERIFIED saving is credited, because a ledger with a guess in it is not worth trusting.
A credit's total is the sum of the months the bill showed it held, never a figure projected
forward. Whether the ledger may rank individuals is OPEN-27; recommended: teams only.

## Status of this document

Planned. Specified in the [P11 spec](../specs/2026-10-08-p11-owners-and-savings-ledger-design.md)
and planned as TASK-P11-006 to TASK-P11-008 in the [P11 plan](../plans/P11-implementation-plan.md),
on 2026-10-08, waiting for the owner's approval to build. The sections a built feature carries are
written when it is built.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P11.
