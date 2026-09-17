# FEAT-028: Recommendation lifecycle

| Field | Value |
| --- | --- |
| Sub project | P3 |
| Status | Planned |
| Specification | Not written. This document expands when P3 is specified |
| Tasks | Not planned |
| Refresh cadence | Live |

## What it does

Moves every recommendation through open, accepted, in progress, done and verified or regressed, with a named owner and a ticket.

## Why it exists

ISS-028. Recommendations without a workflow are ignored, every time. This is not a nice to have, it is the difference between a report and a saving.

## What is already known

**Severity is derived from the money**, per ADR-0016. `CRITICAL` at 1,000 USD a
month or more, `HIGH` at 100, `MEDIUM` at 20, `LOW` below. Never entered by
hand, so a person cannot raise a finding's priority by believing in it more
strongly.

Two rules matter more than the thresholds. **Confidence is tracked separately**,
because a 5,000 USD finding at 40 percent confidence is not the same as one at
95 percent. And **findings are grouped by cause before ranking**, because four
hundred findings at 15 USD each are `LOW` individually and 6,000 USD together,
and a systemic problem must not hide as four hundred trivial ones.

Ticketing target is OPEN-05. Target is above 80 percent reaching a terminal state within 30 days.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P3 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P3.
