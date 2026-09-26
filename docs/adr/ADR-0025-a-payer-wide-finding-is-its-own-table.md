# ADR-0025: A payer wide finding gets its own table, not a row in `recommendation`

Date: 2026-09-26
Status: Accepted

## Context

FEAT-055 turns commitment coverage into findings somebody owns. The value of doing so
is entirely in the machinery `recommendation` already carries: a lifecycle, an owner, a
ticket reference, a severity from money per ADR-0016, and a realized saving measured
afterwards by FEAT-041. A coverage percentage on a chart is a fact nobody owns; a
finding gets worked.

So the obvious implementation is rows in `recommendation`, and TASK-P1-022 was written
assuming it.

It does not work, and the reason is a scoping rule that was already decided.

**`commitment_coverage` is `PayerWide`.** `finops_api/guards.py` says why, in the
docstring of the rule itself: a commitment is bought at the payer and cannot be
apportioned to the accounts that consumed it, so showing it to a viewer restricted to
two accounts would tell them the size of the organization's commitment position, which
is exactly what their scope was meant to withhold. A narrowed scope reads nothing
rather than reading everything, and the screen's job is to say the figure needs
organization wide scope.

**`recommendation` is `ByAccount("sub_account_id")`.** A recommendation names the
account its resource lives in, and a caller narrowed to that account sees it.

**A finding derived from a payer wide fact is payer wide.** Its dimension is `SERVICE`
or `REGION`, never an account, so there is no account to put in the column honestly.
Writing one anyway means choosing an account to stamp on it, and whoever holds that
account then reads the organization's commitment position through a findings list. That
is the disclosure `PayerWide` exists to prevent, arriving through a different table.

Three options were considered.

1. **Stamp the payer account on the row.** One table, all the machinery, no new
   revision. Rejected: a reader granted only the payer account is a narrowed scope, and
   the rule says a narrowed scope reads nothing. Defensible on the grounds that whoever
   holds the management account is the person who buys commitments, and that is an
   argument for changing the rule rather than for quietly excepting one feature from it.
2. **A per class rule inside `recommendation`.** Rejected on ADR-0009's reasoning: two
   implementations of one authorization rule is how an authorization bug is created, and
   a table whose scoping depends on a column value is two rules.
3. **A payer wide table of its own.** Accepted.

## Decision

`commitment_action`, its own table, registered `PayerWide` in `SCOPED_TABLES`. It
carries the lifecycle, owner and ticket columns `recommendation` carries, with the same
vocabulary and the same check constraint text.

A finding inherits the scoping of the fact it was computed from, not the scoping of the
table it resembles.

## Consequences

**The lifecycle vocabulary exists in two places.** That is the price. It is held by a
check constraint in both, copied verbatim, and a test asserts the two sets are equal, so
they cannot drift into meaning different things by DONE. If a third payer wide finding
class appears, the vocabulary should move to a lookup table both reference rather than
being copied a third time.

**FEAT-041's realized saving does not reach these findings yet.** Measuring whether a
commitment purchase delivered needs a second path, because the existing one joins
`recommendation` to cost by resource and a commitment has no resource. Recorded as an
issue rather than built, because the measurement is only meaningful after a term has run
and no term has started.

**The top actions panel reads two sources.** FEAT-052 ranks `recommendation` rows. A
commitment action is the largest single finding most estates will have, so leaving it out
would make the panel wrong about what to do first. It reads both, and a reader without
organization wide scope sees the panel without the commitment half, which the panel says
rather than leaving a gap.

**A narrowed reader is told the figure needs wider scope.** Not shown an empty list,
which would say the estate has no uncovered commitment baseline. That is the same
distinction `graph_coverage` draws between unread and empty, and it is the reason this
decision was worth the second table.
