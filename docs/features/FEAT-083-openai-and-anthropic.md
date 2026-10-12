# FEAT-083: OpenAI and Anthropic cost and usage beside the AWS bill

| Field | Value |
| --- | --- |
| Sub project | P13 |
| Status | Delivered |
| Specification | [P13 spec](../specs/2026-10-12-p13-finops-for-ai-design.md), sections 5.1, 5.3 and 5.5 |
| Tasks | TASK-P13-001, TASK-P13-004 and TASK-P13-005 |
| Decisions | ADR-0036, OPEN-31 |
| Issues addressed | ISS-285 |
| Refresh cadence | Daily, the billing period to date |

## What it does

Reads each connected OpenAI and Anthropic organization's cost report into `cost_focus_daily` as
FOCUS rows, and its usage report into `ai_usage_daily`, so the two largest model APIs sit beside
the AWS bill in every view of spend.

## Why it exists

Model API spend is billed outside AWS, so Meter never saw it, and a view of AI spend without it
shows a fraction of the money.

## How it works

Built: the path, TASK-P13-001, and OpenAI, TASK-P13-004: `ai_provider_account`, the key
reader, `finops_providers/openai/reports.py` over the costs and completions usage reports, the
`openai_usage` collector and `scripts/ops/connect_ai_provider.py`; and Anthropic, TASK-P13-005:
`finops_providers/anthropic/reports.py` over the cost report, whose amounts are cents, and the
messages usage report, which counts no requests, and the `anthropic_usage` collector. One NAT gateway in the hub's first public subnet is the
private route table's one default route, and only the worker's security group, `worker_internet`,
has a rule that uses it, HTTPS to anywhere. Every other task still reaches nothing outside AWS.
`make first-contact` reads a provider's day of costs when its key's secret is named, and
`docs/runbooks/ai-providers.md` has the owner's steps; the demo connects a fake organization of
each provider, TASK-P13-009.

`ai_provider_account` names each organization a tenant connects and the Secrets Manager secret,
under `meter/<env>/ai/`, that holds its admin key. An httpx adapter per provider reads the period
to date from the cost and usage reports, paginated, through the NAT gateway only the worker can
use. Cost rows carry `ingest_source` openai or anthropic, the organization as the billing account
and the project or workspace as the sub account, and the run's delete removes only its own
organization's withdrawn rows.

## Data sources and freshness

| Source | Cadence | Best possible freshness |
| --- | --- | --- |
| OpenAI cost and completions usage reports | Daily | The provider's daily buckets |
| Anthropic cost report and messages usage report | Daily | The provider's daily buckets |

`as_of` is the end of the bucket; `collected_at` is when the run read it.

## Measured or modelled

Cost, tokens and requests are measured, as the provider reports them.

## Failure behaviour

401 and 403 are AccessDenied, 429 Throttled after bounded retries, a timeout or a 5xx Unreachable,
and a body without the fields the mapping needs SchemaDrift. An organization that fails shows its
cause and its last good figures with their age, never a zero.

## Security considerations

The admin key is read at run time and appears in no setting, log, error or row. The worker's role
reads secrets under `meter/<env>/ai/` only. A provider row's sub account names no scope grant, so
its cost is visible at global scope only.

## Interface

`scripts/ops/connect_ai_provider.py`, `GET /v1/ai/spend`, and the AI spend screen.

## Not doing

Spend caps or key revocation, which would be writes. Providers beyond these two.
