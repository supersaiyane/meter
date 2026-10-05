# FEAT-064: Navigation by the FinOps Framework and FOCUS names on every screen

| Field | Value |
| --- | --- |
| Sub project | P8 |
| Status | Planned |
| Specification | [P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), sections 5.2 and 5.3 |
| Tasks | TASK-P8-002 and TASK-P8-004 |

## What it does

Arranges the screens in the groups the owner approved, each answering to a FinOps Framework
domain: Overview, Analyze, Plan, Optimize, Govern, Inventory, Report, Assist and Platform. A
cost column takes its FOCUS display name, a screen or a KPI takes its Framework name, and the
provider's own word, such as Amortized, Unblended or Savings Plan, stays in the column's
tooltip. Every old path redirects to its new home, so a bookmark, a digest link or a link in a
pull request body still lands.

## Why it exists

The owner said on 2026-10-05 that the screens do not use standard FinOps nomenclature, and an
audit of every screen the same day confirmed it. The labels paraphrase rather than name: FOCUS
`EffectiveCost` reads as "Amortized" or "Total spend", commitment utilization reads as "Of what
we paid for, used", and the words showback, chargeback, coverage and effective savings rate
appear nowhere. Practitioners search for both the standard term and the provider's, which is
why the provider's word stays one hover away.

## What is already known

FinOps Score moves into Plan, beside the budgets it is read with, because the Framework places
KPIs and Benchmarking there, and Unit Economics is listed as arriving, never as built. Screens
that merge become tabs: Organization under Accounts, Geography under Topology, and the three
query cost screens under Query Cost. ADR-0020 fixed seven groups and said renaming one takes an
ADR, so TASK-P8-002 writes the ADR that supersedes it. The full label table, one row per label
on every screen, is TASK-P8-004's first output, approved by the owner before any label changes.

## Status of this document

Planned. The feature is specified in the
[P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), sections 5.2 and 5.3, and
planned as TASK-P8-002 and TASK-P8-004 in the [P8 plan](../plans/P8-implementation-plan.md),
both pending the owner's approval. The sections a built feature carries, how it works, its
failure behaviour, its security considerations, its interface and what it does not do, are
written when it is built. Recording only what is decided is deliberate: a document that invents
detail ahead of the build is worse than a short one, because it will be believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P8.
