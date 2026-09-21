# FEAT-043: FinOps Score, decomposable to the findings that moved it

| Field | Value |
| --- | --- |
| Sub project | P3 |
| Status | Delivered |
| Specification | [P3 spec](../specs/2026-09-20-p3-utilization-and-rightsizing-design.md), section 9 |
| Tasks | TASK-P3-015, TASK-P3-016, TASK-P3-019 |
| Refresh cadence | 6 hours |
| Source | Adopted from a competitive review on 2026-08-23, over an objection |

## What it does

A single 0 to 100 score for optimisation posture, per account and per team, recalculated every six hours.

## Why it exists

It gives an executive a number and a team a trend. It was adopted on the project owner's decision after I argued against it, on the grounds that a composite number nobody can decompose tells you nothing about what to do.

## What is already known

**The objection became the condition.** This ships only if the score decomposes. Every score shows its components, every component links to the findings that moved it, and a change between two runs is explainable as a list of findings that opened or closed. A score that cannot be taken apart is not shipped.

It does not replace the north star metric. Realized savings, confirmed against CUR 60 days after a recommendation is marked done, remains the measure of whether Meter is worth running. The score measures posture, which is a different and easier thing.

## How it works

A 0 to 100 score for optimisation posture, per account and per team, recalculated
every six hours from the open findings and their money.

**The objection became the ship condition.** This ships only if the score
decomposes. `score()` returns components, never a bare number; every component names
the findings that produced it; and a change between two runs resolves to a list of
findings that opened or closed. A score that cannot be taken apart is not a score,
it is an opinion with a number on it.

Each run stores its components, not only its total, which is what makes the
difference between two runs explainable rather than merely visible.

## Failure behaviour

**A scope with no findings has no score, rather than a score of 100.** A perfect
score for an estate nobody has looked at is the worst possible output of this
feature, and it is the output a naive implementation produces on its first day.

## Security considerations

Scoped by account, and the team level score is computed from the same tag
allocation the cost screens use, so a score and a bill attribute to the same owner.

## Interface

`GET /waste/score` and `/waste/score`. The components are on the same screen as the
score, not behind a link, and each links to the findings that moved it.

## Not doing

**Benchmarking against other organizations.** A score is only meaningful against
its own history here, and a comparison against an anonymised cohort is a different
product with different data protection questions.
