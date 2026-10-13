# FEAT-090: Plan approval, the purchase recorded and verified against the bill

| Field | Value |
| --- | --- |
| Sub project | P14 |
| Status | In build |
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

Built, TASK-P14-008. A person whose scope is the organization approves a draft, records an approved plan as bought, or withdraws a draft or an approved plan, each with a note. Each step is a `purchase_plan_event` row with the person, the time and the note, and an audit row ALLOWED; a narrowed person is refused with a 403, audited DENIED. A step the plan's status does not allow is refused with a 409 that says why, and the database refuses it too, through migration 0057's trigger and the event's check, constraint 11. A plan that buys nothing this month cannot be approved. The status changes only if it is still what was read, so two people acting at once cannot both move it.

What is approved and bought is the plan's own month's tranche; the later tranches are named for information and are drafted again in their own months. Each day the plan collector matches each line of a bought plan to a Savings Plan the inventory holds: the same program, term and payment option, the same family and Region for an EC2 Instance line, an hourly commitment within one percent of the line's, and a start after the approval. Each commitment pays for one line at most, held by migration 0058's unique index. When every line is matched the plan is verified, a step the collector records. A draft not approved within its month lapses.

An erasure keeps each step and replaces the person's name on it.

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

`POST /v1/commitments/plans/{id}/approve`, `/bought` and `/withdraw`, built, each taking a note and answering with the plan, its lines with any matched commitment, and its steps. `GET /v1/commitments/plans` carries the steps too. The plans panel's actions, TASK-P14-009, offer only the steps the plan's status allows, each with a required note, to a payer only, and show a refusal in the API's own words.

## Not doing

Making the purchase. A person buys in AWS.
