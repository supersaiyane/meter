# FEAT-081: Bedrock cost by model, token type, application and IAM principal, from the bill

| Field | Value |
| --- | --- |
| Sub project | P13 |
| Status | Delivered |
| Specification | [P13 spec](../specs/2026-10-12-p13-finops-for-ai-design.md), sections 5.2, 5.3 and 5.7 |
| Tasks | TASK-P13-002 and TASK-P13-007 |
| Decisions | OPEN-34 |
| Issues addressed | None yet |
| Refresh cadence | The cost collector's, unchanged |

## What it does

Reads each Bedrock line item in the bill with its usage type, model, token type, token count and
the IAM principal that made the request, and lets a person group Bedrock spend by any of them and
by the application inference profile or resource tag that names a feature.

## Why it exists

A Bedrock charge lands in Meter as a cost row like any other, so the most common question about AI
spend, which model and whose calls, has no answer, and `cost_focus_daily` has no column for any of
the fields that would give one.

## How it works

Built: the columns, TASK-P13-002; `GET /ai/spend`, TASK-P13-007, which groups the bill's AI lines
by model, token type, feature or IAM principal; and the AI spend screen, TASK-P13-008. The demo
bills two Bedrock features, TASK-P13-009.

`finops_providers/aws/cur.py` asks the export's catalog for `x_usagetype` and
`line_item_iam_principal` the way it asks for the split cost columns, and reads them where they
exist. A pure parser beside it, `finops_providers/aws/bedrock_usage.py`, reads the model and token
type from the usage type's suffix; it is AWS's knowledge, and ADR-0028 keeps vendors out of
`finops_core`.
The cost collector writes them to five nullable `x_` columns of `cost_focus_daily`, beside a Meter
column `ingest_source` that keeps each source's restatement to its own rows.

## Data sources and freshness

| Source | Cadence | Best possible freshness |
| --- | --- | --- |
| The AWS FOCUS export | The cost collector's | AWS writes the export several times a day |

`as_of` is the charge period's end; `collected_at` is when the collector read it.

## Measured or modelled

Cost, tokens and principals are measured, read from the bill. Cost per thousand tokens divides
measured cost by measured tokens of the same rows, so it is measured.

## Failure behaviour

A usage type the parser does not recognise leaves the AI columns null: the cost still counts and
shows as Bedrock without a model, never as a model it might be. An export without the columns reads
as before, with the breakdown marked unavailable.

## Security considerations

The IAM principal is an ARN in the customer's account. It is read under the scope that already
governs the row's account.

## Interface

`GET /v1/ai/spend` grouped by model, token type, feature or caller, and the AI spend screen.

## Not doing

Pricing tokens from the price list: the bill's own cost is the figure. Renaming the `x_` columns
before FOCUS 1.5 is published.
