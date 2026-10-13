# FEAT-090: Plan approval, the purchase recorded and verified against the bill

| Field | Value |
| --- | --- |
| Sub project | P14 |
| Status | Specified |
| Specification | [P14 spec](../specs/2026-10-13-p14-commitments-design.md), section 5.2 |
| Tasks | TASK-P14-008 and TASK-P14-009 |
| Decisions | OPEN-36 |
| Issues addressed | None yet |
| Refresh cadence | Daily, for verification |

## What it does

Moves a plan from draft to approved to bought, each step recorded with the principal, the time and a note, and verifies a bought plan by finding its commitment in the inventory.

## Why it exists

A recommendation nobody owns is never acted on, and one acted on is never checked. The approval is the owner's decision on the record; the verification is what makes the saving a fact rather than a forecast.

## How it works

Not built yet. `purchase_plan_event` records each transition; a check refuses a transition out of order. The plan collector matches each bought line to a new commitment by program, term, payment option and hourly commitment within one percent, starting after the approval. A draft not approved within its month lapses.

## Data sources and freshness

| Source | Cadence | Best possible freshness |
| --- | --- | --- |
| Meter's tables and the inventory | Daily | The day before |

## Measured or modelled

Measured: the matched commitment and its saving from the bill. The plan's own figures stay modelled.

## Failure behaviour

A line matched to nothing stays bought and is shown as not yet seen, never as verified.

## Security considerations

Only a principal whose scope is global may approve, record a purchase or withdraw, because a commitment belongs to the payer. Meter never calls a purchase API, constraint 6.

## Interface

`POST /v1/commitments/plans/{id}/approve`, `/bought` and `/withdraw`, and the plans panel's actions.

## Not doing

Making the purchase. A person buys in AWS.
