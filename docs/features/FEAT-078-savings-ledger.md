# FEAT-078: The savings ledger, verified savings credited and re-measured

| Field | Value |
| --- | --- |
| Sub project | P11 |
| Status | Planned |
| Specification | [P11 spec](../specs/2026-10-08-p11-owners-and-savings-ledger-design.md), sections 5.5 and 5.6 |
| Tasks | TASK-P11-006 to TASK-P11-008; TASK-P11-006 and TASK-P11-007 done 2026-10-11 |

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
forward. Whether the ledger may rank individuals was OPEN-27, answered on 2026-10-08: teams only.

## How it works

The daily `savings_ledger` collector, P11 spec section 5.5, reads only what Meter holds and makes
no AWS call. For each VERIFIED row in `realized_saving` whose recommendation has an owner it writes
one `savings_credit`, migration 0043: the recommendation's owner, which no move after DONE changes;
the team its strongest team suggestion names, the catalogue's, a tag's, or failing both the
resource's `team` tag; the actor of its DONE event; and the verified monthly saving, FEAT-029's
before window's cost less its after window's, thirty days each, measured, dated by the after
window's end. The names are fixed when the credit is first written and later runs refresh only the
figure and its dates, so a reorganisation does not move a past saving to another team. TASK-P11-006
built the table and the collector, run by the demo seed after the owners.

Every closed month after verification is then judged, `finops_query.ledger`, into
`savings_credit_month`, migration 0044: the resource's cost that month against the cost before the
change at FEAT-029's daily rate, the before window's cost over its thirty days. A month the account
was billed and the resource cost less is HELD with the difference, measured, and a resource absent
from a billed month cost nothing; one that cost as much or more is REGRESSED and the credit stops
there; a month the account's bill holds nothing for is UNOBSERVED. A credit's total is the sum of
its held months. TASK-P11-007 built this, spec section 5.5 as amended on 2026-10-11.

## Failure behaviour

A verdict that stops being VERIFIED, because late rows in the bill moved a window, withdraws its
credit rather than leaving it standing. A saving whose recommendation has no owner is credited to
nobody, since the ledger credits only an owner a person assigned. A verification cannot be deleted
while a credit rests on it, nor a credit while a month does: a withdrawn credit's months go first.
An unobserved month carries no figure, never a zero, and late rows in the bill correct a month on
the next run. The collector reads the database only, so it has no account to fail on; a run that
cannot write fails whole and is retried, never half written.

## Security considerations

Read only, constraint 6. Credits are scoped by the account of the recommendation, `ByAccount`, so a
reader sees only the credits for accounts they can see. A credit names the owner and the person who
closed the work, so it is classed as holding personal identifiers; the ledger screen ranks teams
and never individuals, OPEN-27.

## Interface

The `savings_credit` table now, read by the ledger's routes and screen in TASK-P11-008:
`GET /savings/ledger` and `GET /savings/ledger/credits`, both exportable, and a Savings ledger
screen under Optimize with every figure labelled measured.

## Not doing

- Crediting an INCONCLUSIVE or REGRESSED verdict, or a saving nobody owned.
- Projecting a saving forward: a credit totals the months the bill showed it held.
- Judging a month before it has closed, or after the credit regressed.
- Ranking individuals, OPEN-27.

## Status of this document

In build. Approved by the owner on 2026-10-08 with teams only. TASK-P11-006 built the credits on
2026-10-11 and the months they held, TASK-P11-007, the same day; the ledger's routes and screen,
TASK-P11-008, follow. Specified in the [P11 spec](../specs/2026-10-08-p11-owners-and-savings-ledger-design.md)
and planned in the [P11 plan](../plans/P11-implementation-plan.md).

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P11.
