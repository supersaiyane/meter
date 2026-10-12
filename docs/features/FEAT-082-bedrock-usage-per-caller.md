# FEAT-082: Bedrock usage per caller from invocation logs

| Field | Value |
| --- | --- |
| Sub project | P13 |
| Status | In build |
| Specification | [P13 spec](../specs/2026-10-12-p13-finops-for-ai-design.md), section 5.4 |
| Tasks | TASK-P13-003 and TASK-P13-007 |
| Decisions | OPEN-32 |
| Issues addressed | None yet |
| Refresh cadence | Daily, for the day before |

## What it does

Where an account sends Bedrock invocation logs to CloudWatch Logs, records each day's requests and
tokens per caller, model and application, and prices them at the bill's unit cost for that model
and token type.

## Why it exists

The bill names the IAM principal, which is usually a shared role, so it cannot say which person or
agent spent the money. The invocation log names the caller's ARN and the metadata the caller
attaches, which is where an application or an agent names itself.

## How it works

Built so far: the collection, TASK-P13-003, and `GET /ai/callers`, TASK-P13-007, each caller's tokens
priced at the bill's unit cost for the same model, token type and day, matched by
`finops_query.ai.model_key` because a log names a model by its identifier and the bill by its
usage type.

For each account and collection Region the collector reads the invocation logging configuration.
Where it names a CloudWatch log group, it runs one Logs Insights query whose every output is an
aggregate, requests and four token counts by caller, model and the request metadata key the
setting `ai_request_metadata_key` names, and writes the result to `ai_usage_daily`.

## Data sources and freshness

| Source | Cadence | Best possible freshness |
| --- | --- | --- |
| Bedrock invocation logs in CloudWatch Logs | Daily | The day before |

`as_of` is the end of the day read; `collected_at` is when the query ran.

## Measured or modelled

Requests and tokens are measured. Cost per caller is modelled: measured tokens priced at the unit
cost the bill shows for the same model, token type and day.

## Failure behaviour

An account whose logging names no CloudWatch log group reads NotOptedIn, with the step that enables
it, and its callers are absent, never zero. A query refused by the role's log group pattern is
AccessDenied, naming the StackSet parameter.

## Security considerations

Invocation logs hold every prompt and response. Meter's query returns aggregates only, held by a
test that fails the gate if it names a body field, and the collector role may start a query only on
log groups matching `InvocationLogGroupPattern`. A caller's ARN can name a person, so
`ai_usage_daily.caller` is class P.

## Interface

`GET /v1/ai/callers`, and the caller view of the AI spend screen.

## Not doing

Reading logs delivered only to S3. Reading a prompt, a response or a sample of either.
