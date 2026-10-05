# FEAT-065: Cost Explorer, two group bys over FOCUS dimensions and tags

| Field | Value |
| --- | --- |
| Sub project | P8 |
| Status | Planned |
| Specification | [P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), sections 5.3 and 7 |
| Tasks | TASK-P8-007 |

## What it does

`GET /cost/explore` and its screen answer the question a practitioner asks first, with the rows
the product already holds. A person groups cost two ways at once over FOCUS dimensions and tag
keys from an allow list, filters it, and reads it daily or monthly over month to date, 3, 6 or
12 months, year to date or a custom period, compared with the previous period. Effective Cost is
the default, and another cost metric is offered only where the table holds it.

## Why it exists

The owner said on 2026-10-05 that there is no graphical dashboard or report a person can take
away, and the audit the same day found no chart library and no screen called a report or a
dashboard. Today's Spend and trend screen becomes Cost Explorer under Analyze, named for the
Framework's Reporting and Analytics capability and for AWS Cost Explorer.

## What is already known

It sits behind the same scope dependency and repository guard as `/cost`, carries coverage and
failures in the envelope, and shows unallocated cost rather than hiding it. The query is
bounded, with partition pruning on the period and a row limit the envelope names. No figure is
computed differently: it reads rows the API already holds, and its Excel and CSV export is
FEAT-067's.

## Status of this document

Planned. The feature is specified in the
[P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), sections 5.3 and 7, and
planned as TASK-P8-007 in the [P8 plan](../plans/P8-implementation-plan.md), both pending the
owner's approval. The sections a built feature carries, how it works, its failure behaviour,
its security considerations, its interface and what it does not do, are written when it is
built. Recording only what is decided is deliberate: a document that invents detail ahead of
the build is worse than a short one, because it will be believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P8.
