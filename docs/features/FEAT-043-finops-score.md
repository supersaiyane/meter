# FEAT-043: FinOps Score, decomposable to the findings that moved it

| Field | Value |
| --- | --- |
| Sub project | P3 |
| Status | Planned |
| Specification | Not written. This document expands when P3 is specified |
| Tasks | Not planned |
| Refresh cadence | 6 hours |
| Source | Adopted from a competitive review on 2026-08-23, over an objection |

## What it does

A single 0 to 100 score for optimisation posture, per account and per team, recalculated every six hours.

## Why it exists

It gives an executive a number and a team a trend. It was adopted on the project owner's decision after I argued against it, on the grounds that a composite number nobody can decompose tells you nothing about what to do.

## What is already known

**The objection became the condition.** This ships only if the score decomposes. Every score shows its components, every component links to the findings that moved it, and a change between two runs is explainable as a list of findings that opened or closed. A score that cannot be taken apart is not shipped.

It does not replace the north star metric. Realized savings, confirmed against CUR 60 days after a recommendation is marked done, remains the measure of whether Meter is worth running. The score measures posture, which is a different and easier thing.

## Status of this document

Planned. The remaining sections are written when P3 is specified. Recording
only what is decided is deliberate: a document that invents detail ahead of the
decision is worse than a short one, because it will be believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P3, and
[docs/11-COMPETITIVE-REVIEW.md](../11-COMPETITIVE-REVIEW.md).
