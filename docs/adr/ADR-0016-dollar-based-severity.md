# ADR-0016: Severity on a cost finding is the money

Date: 2026-08-23
Status: Accepted

## Context

The project uses one severity vocabulary everywhere: `CRITICAL`, `HIGH`,
`MEDIUM`, `LOW`. It works well for defects and security findings, where impact
is a judgement.

It works badly for a cost recommendation. "High priority rightsizing" means
nothing without a number, and whoever writes the finding picks the label, so
the ranking reflects the author rather than the impact. A competitive review on
2026-08-23 found a product using explicit dollar thresholds instead, and the
idea is better than ours.

## Decision

**A cost finding's severity is derived from its monthly impact, not chosen.**

| Severity | Monthly impact | Rationale |
| --- | --- | --- |
| `CRITICAL` | 1,000 USD or more | Worth interrupting planned work |
| `HIGH` | 100 USD or more | Worth a ticket this sprint |
| `MEDIUM` | 20 USD or more | Worth batching with similar findings |
| `LOW` | Below 20 USD | Worth fixing only while already in the file |

Derived, never entered. A person cannot raise the severity of a finding by
believing in it more strongly.

Two rules follow, and both matter more than the thresholds.

**Confidence is separate from severity.** A 5,000 USD finding at 40 percent
confidence is not the same as a 5,000 USD finding at 95 percent, and collapsing
the two into one label loses the difference. Every finding carries both, plus
its `measured`, `modelled` or `forecast` flag.

**Aggregation before ranking.** Four hundred findings at 15 USD each are `LOW`
individually and 6,000 USD together. Findings are grouped by cause, and the
group carries the summed impact, so a systemic problem does not hide as four
hundred trivial ones. This is the failure mode the thresholds would otherwise
introduce.

Defect and security severity is unchanged. `docs/05-SECURITY.md` keeps its own
vocabulary, and a security finding is never assigned a dollar value, because
"this vulnerability is worth 40 USD a month" is not a sentence anyone should
write.

## Consequences

Positive.

- The recommendation list is ranked by money without anyone deciding a ranking.
- Two teams looking at the same finding read the same severity.
- The thresholds are configurable per tenant, because 100 USD a month is
  material to one organization and rounding error to another.

Negative.

- The severity of a finding moves when its estimate moves, so a finding can
  change severity without anything about it changing. Mitigated by showing the
  impact alongside the label, which makes the movement legible.
- Two severity vocabularies now exist, cost and defect, and a reader must know
  which they are looking at. Mitigated by never mixing them in one list.

## Alternatives rejected

**One vocabulary for everything.** Rejected. It is what we had, and it produced
labels that carry no information on the cost side.

**Rank purely by dollars, with no severity label.** Tempting and nearly right.
Rejected because a label is what makes a finding sortable, filterable, and
alertable, and because "everything above CRITICAL" is a threshold people can
set where "everything above the 94th percentile of dollar impact" is not.
