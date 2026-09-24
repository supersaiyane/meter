# FEAT-015: Query cost kill switch

| Field | Value |
| --- | --- |
| Sub project | P2 |
| Status | Specified |
| Specification | [P2 spec](../specs/2026-08-23-p2-query-cost-governance-design.md) |
| Tasks | Not planned |
| Refresh cadence | Event driven, seconds to minutes |

## What it does

Detects a runaway query pattern in near real time and stops it: counts CloudTrail `StartQuery` per principal per hour, alerts on breach, and applies a deny policy through AWS Budgets Actions at threshold.

## Why it exists

A six hour audit of the original failure would still have let roughly 25,000 USD burn between sweeps. Prevention cannot run on a survey cadence.

## How it works

An EventBridge rule on CloudTrail `StartQuery` counts executions per principal per rolling hour. On breach it always writes an `enforcement_action`, pages, and raises a ticket. Above `alert` it may throttle after a grace window, and above `throttle` it may apply a Budgets Action deny policy on `logs:StartQuery` for that principal.

## What is already known

EventBridge rule on CloudTrail. This is deliberately a separate feature from the audit, at a separate cadence. See ADR-0012.

## Failure behaviour

The control runs as a Lambda rather than on Fargate because it must respond in seconds and is idle between events. A failure to apply an enforcement action still records the attempt and pages, because the alert is the part that always happens.

## Security considerations

**Two rules enforced by the database, not by intention.** A `DENY` action cannot be written without an expiry, so a deny cannot become permanent by being forgotten. And a never deny list exists, because cutting an engineer off from Logs Insights during an outage, caused by that outage, is a self inflicted second incident. Default expiry is 60 minutes.

## Interface

`GET /api/v1/query/enforcement` and `POST /api/v1/query/enforcement/{id}/revoke`, the break glass path. Level is set per tenant by the `query_control_level` flag, defaulting to `alert`. See [P2 spec](../specs/2026-08-23-p2-query-cost-governance-design.md) section 7.2.

## Not doing

Does not act on anything other than CloudWatch Logs Insights query volume. Broader spend control is AWS Budgets and belongs in P1.
