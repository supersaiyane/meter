# FEAT-059: An application layer on the topology graph

| Field | Value |
| --- | --- |
| Sub project | P6 |
| Status | Planned |
| Specification | None. [competitive review](../11-COMPETITIVE-REVIEW.md) 2026-09-26, sized Large |
| Tasks | None. Deliberately unscheduled, see below |
| Source | Adopted in principle from the IBM Turbonomic review on 2026-09-26 |

## What it does

Nothing yet. It would group resources by the business application they serve, so a cost could
be attributed to an application rather than to an account and a tag.

## Why it exists

It is the honest prerequisite for the executive view the review also names. The one page a
director reads is a page about applications, not about instances, and we cannot produce it
without knowing which resources make up an application.

**It is unscheduled on purpose.** It needs either a tag convention we do not enforce or an APM
target we do not integrate with, and both are decisions about what a customer must do before
the feature works.

The failure to avoid is the one every tagging feature hits: a partial convention produces an
application map covering sixty percent of the estate, and the forty percent outside it is
invisible rather than marked. On present evidence that would be recorded as coverage, the same
way `graph_coverage` records an unread slice, because an application map that quietly omits
the untagged resources is the same class of defect as a graph that draws a refused region as
sparse.

Sequenced after FEAT-058 because a performance dimension changes what an application level
view would be reporting, and building the view first would mean designing it twice.
