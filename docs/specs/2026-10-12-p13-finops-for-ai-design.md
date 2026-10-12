# P13 FinOps for AI: design specification

Date: 2026-10-12
Status: Approved by the owner on 2026-10-12 with OPEN-31 to OPEN-34 answered, in build. Chosen the same day as the next priority, proposal 2 of `next-in-scope.txt`
Sub project: P13
Features: FEAT-081, FEAT-082, FEAT-083, FEAT-084, FEAT-085
Depends on: P1 for the bill, P3 for utilization, P12 for the composition every new collector joins. Proof against a real estate waits on ISS-002, an AWS account, and ISS-285, an admin key from each AI provider
Supersedes: nothing. ADR-0036 amends ADR-0035's network path

## 1. Purpose

Spend on models is the fastest growing line on most bills Meter will read, and Meter cannot say
what any of it bought. A Bedrock charge lands as a cost row like any other, with nothing naming
the model, the kind of token or who called it; the OpenAI and Anthropic bills never reach Meter at
all; and a GPU instance shows its cost but never whether the GPU did anything. P13 makes AI spend
legible: Bedrock by model, token type, application and caller, the two largest model APIs beside
the AWS bill in the same FOCUS table, GPU hours and cost with utilization where it is published,
and one screen that shows cost per token, per request and per feature, each figure labelled
measured or modelled.

## 2. Definition of done

- A Bedrock line item in the bill is read with its usage type, model, token type, token count and
  IAM principal, where the export carries them, into `x_` columns of `cost_focus_daily`.
- Where an account sends Bedrock invocation logs to CloudWatch Logs, Meter records tokens and
  requests per caller, model and application from an aggregate query that never reads a prompt or
  a response; where it does not, the account reads NotOptedIn.
- OpenAI and Anthropic cost lands in `cost_focus_daily` as FOCUS rows, and their token usage per
  model, project or workspace, and key lands beside Bedrock's, through a NAT gateway only the worker
  can use.
- GPU instances show hours and cost from the bill, and utilization from the CloudWatch agent's
  NVIDIA metrics where published, and read as not published, never as zero, where not.
- One screen shows AI spend by provider, model, token type, feature and caller, with cost per
  thousand tokens and per request, and the GPU fleet.

## 3. Out of scope

- Spend caps, budgets per key, and blocking a call: Meter is read only in v1, constraint 6.
- Choosing a model for a workload, or comparing model quality.
- Providers beyond Bedrock, OpenAI and Anthropic, and GPU clouds beyond AWS.
- SageMaker and EKS GPU utilization: their hours and cost come from the bill like EC2's, and only
  an EC2 instance's utilization is read.
- The prompts and responses themselves, in any form, at any time.
- An MCP tool for AI spend. The MCP server reaches the new endpoints when a tool is added for them,
  through the API like every other tool, ADR-0009.
- Renaming the `x_` columns to FOCUS 1.5's names, which waits for 1.5 to be published.

## 4. The gap, measured on 2026-10-12

- `finops_providers/aws/cur.py` reads 28 FOCUS columns, 9 split cost allocation columns and 5 FOCUS
  1.2 columns (measured). None names a usage type, an IAM principal, a model or a token type, and
  `cost_focus_daily` has no column for any of them.
- No table holds a token or a request count.
- The only HTTP clients in the code reach Meter's own API and Grafana: `finops_api/toolbox.py`,
  `finops_api/exports/scheduled.py`, `finops_mcp/api.py` and `finops_providers/grafana/client.py`.
  The hub's private route table has no default route, `infra/terraform/hub/network.tf`, so a task
  can reach nothing outside AWS, ADR-0035.
- The cost collector's restatement delete, `RETRACT` in `finops_ingest/collectors/cost_focus.py`,
  removes every row of a tenant's billing period that its run did not write. A second source
  writing to `cost_focus_daily` would be deleted by the next AWS cost run.
- The collector role, `infra/terraform/member/collector_role.yaml`, reads CloudWatch metrics,
  `cloudwatch:GetMetricData` and `cloudwatch:ListMetrics`, and nothing from Bedrock or CloudWatch
  Logs.

## 5. Decisions

### 5.1 The AI providers are reached through a NAT gateway, OPEN-31

OpenAI and Anthropic have no VPC endpoint and the relay of ADR-0035 is for AWS APIs that have
none. The hub gains one NAT gateway in its first public subnet and a default route to it from the
private route table. Only the worker's tasks may use it: the worker gets a security group of its
own whose one rule allows HTTPS, port 443, to anywhere, and the shared task group keeps its egress
to the endpoints, S3, the database and the VPC. The API, the web and the dispatcher still cannot
reach the internet, and the flow logs record any attempt. One gateway rather than one per zone:
a lost zone stops the provider reads until it returns, typed Unreachable, and nothing else.
Modelled at USD 35.04 a month for the gateway at eu-west-1's list price of USD 0.048 an hour, USD
3.65 for its public IPv4 address, and USD 0.048 per GB processed; a day of usage reports is
kilobytes. Tagged `finops:module = network` like the rest of the hub, so the platform meters it.
Recorded in ADR-0036. Answered by the owner on 2026-10-12: NAT gateway.

### 5.2 FOCUS has no token columns yet, so Meter adds `x_` columns, OPEN-34

FOCUS reserves the `x_` prefix for columns a producer adds. `cost_focus_daily` gains five, all
nullable because most rows are not AI:

- `x_usage_type`, the provider's own usage type, AWS's `x_UsageType` in its FOCUS export.
- `x_iam_principal`, the IAM principal that made the request, CUR 2.0's
  `line_item_iam_principal`, where the export carries it.
- `x_ai_model`, `x_ai_token_type` (input, output, cache read or cache write) and `x_ai_tokens`,
  parsed from the usage type for Bedrock and given by the provider for OpenAI and Anthropic.

When FOCUS 1.5 publishes its names, the columns are renamed the way constraint 12 requires: add
the new ones, backfill, and drop the `x_` ones a release later. Answered by the owner on
2026-10-12: `x_` columns now, renamed when FOCUS 1.5 lands.

The bill's AI columns are optional at the source, like the split and FOCUS 1.2 columns, and asked
of the catalog the same way: an export without them is read with the SQL it always was. The usage
type parser is pure and lives in `finops_core`; it reads the model and token type from the
suffixes AWS documents for Bedrock, `-input-tokens`, `-output-tokens`,
`-cache-read-input-token-count` and `-cache-write-input-token-count` and their marketplace forms,
and leaves every column null for a usage type it does not recognise, rather than guessing.

### 5.3 Each source writes and restates only its own rows

`cost_focus_daily` gains a Meter column, `ingest_source`, one of `aws_export`, `openai` or
`anthropic`, defaulting to `aws_export` so every existing row and every writer of the release
before keeps its meaning. Each collector's restatement delete keys on its own source, so the AWS
cost run no longer removes a provider's rows and a provider run never removes the bill's.

### 5.4 Bedrock per caller comes from invocation logs where they are enabled, OPEN-32

The bill names the IAM principal, which is a role far more often than a person or an agent.
Invocation logs name the caller's ARN and carry up to 16 key value pairs the caller attaches,
`requestMetadata`, which is where an application names itself. They also carry the prompt and the
response, so Meter reads them only through a CloudWatch Logs Insights query whose every output is
an aggregate: requests and the four token counts, summed by caller, model and, when the setting
`bedrock_request_metadata_key` names one, that key's value. A test holds the query to aggregates
and fails if it names a body field. The collector reads each account and collection Region once a
day for the day before. An account whose logging configuration names no CloudWatch log group is
NotOptedIn, with the step that enables it; logs delivered only to S3 read the same, because Meter
reads CloudWatch Logs. The collector role may start a query only on log groups matching the
StackSet parameter `InvocationLogGroupPattern`, default `/aws/bedrock/*`, so the reach into a
member account's logs is one the owner chose. Cost per caller is modelled: the caller's tokens
priced at that day's unit cost of the same model and token type in the bill. Answered by the owner
on 2026-10-12: invocation logs where enabled.

### 5.5 OpenAI and Anthropic through their admin APIs

Each provider organization a tenant connects is a row of `ai_provider_account`, naming the Secrets
Manager secret that holds its admin key, under `meter/<env>/ai/`, which is the only path the
worker's role may read. The key never reaches a setting, a log or the database. A run reads the
billing period to date from each provider's cost report, daily buckets, and writes it to
`cost_focus_daily` as FOCUS rows with `provider_name` OpenAI or Anthropic, the organization as the
billing account, the project or workspace as the sub account, and the model and token type in the
`x_` columns where the provider names them. It reads the usage report the same way into
`ai_usage_daily`: tokens and requests by day, model, project or workspace, and key. Errors are
typed: 401 and 403 AccessDenied, 429 Throttled after bounded retries honouring `Retry-After`, a
timeout or 5xx Unreachable, a body without the fields the mapping needs SchemaDrift. An OpenAI
`user_id` is recorded as the caller where the caller sets one.

A provider row's sub account is a project or a workspace, which no scope grant names, so its cost
is visible to a principal with global scope only. Scope that can name a provider project is a later
decision, and until then the conservative reading is the one constraint 3 already enforces.

### 5.6 GPU: the bill for hours and cost, the agent for utilization, OPEN-33

GPU hours and cost are a query over the bill: line items whose usage type names an instance type of
the `p`, `g`, `trn`, `inf` or `dl` families, with or without SageMaker's `ml.` prefix, summed by
resource, with hours from `consumed_quantity`. Utilization is collected daily for each EC2 GPU
instance the bill names, from the CloudWatch agent's `nvidia_smi_utilization_gpu` metric, in the
namespace the setting `gpu_metrics_namespace` names, default `CWAgent`: average and peak across the
instance's GPUs, into `gpu_utilization_daily`. An instance that publishes nothing has no row, and
the screen says not published, never zero. Answered by the owner on 2026-10-12: GPU utilization as
well as hours and cost.

### 5.7 Cost per token, request and feature

A feature is whatever names an application in each source: a Bedrock application inference profile
or a resource tag on the bill, the request metadata key in invocation logs, an OpenAI project and
an Anthropic workspace. Cost per thousand tokens divides a measured cost by measured tokens of the
same rows, so it is measured. Cost per request needs requests, which only the usage reports and the
invocation logs carry, so it is modelled where the cost and the requests come from different
sources, and the screen says which.

## 6. Data model

Four changes, every one additive, constraint 12.

```sql
-- TASK-P13-002
ALTER TABLE cost_focus_daily
    ADD COLUMN ingest_source  TEXT NOT NULL DEFAULT 'aws_export'
        CHECK (ingest_source IN ('aws_export', 'openai', 'anthropic')),
    ADD COLUMN x_usage_type    TEXT,
    ADD COLUMN x_iam_principal TEXT,
    ADD COLUMN x_ai_model      TEXT,
    ADD COLUMN x_ai_token_type TEXT
        CHECK (x_ai_token_type IN ('input', 'output', 'cache_read', 'cache_write')),
    ADD COLUMN x_ai_tokens     NUMERIC(30, 10) CHECK (x_ai_tokens >= 0),
    ADD CONSTRAINT ck_cost_focus_daily__tokens_have_a_type
        CHECK (x_ai_tokens IS NULL OR x_ai_token_type IS NOT NULL),
    ADD CONSTRAINT ck_cost_focus_daily__token_type_has_a_model
        CHECK (x_ai_token_type IS NULL OR x_ai_model IS NOT NULL);

-- TASK-P13-003. An empty string in a key column means the source does not report that
-- dimension, which a NULL cannot say inside a primary key.
CREATE TABLE ai_usage_daily (
    tenant_id          UUID        NOT NULL REFERENCES tenant(tenant_id),
    ingest_run_id      UUID        NOT NULL,
    provider           TEXT        NOT NULL CHECK (provider IN ('bedrock', 'openai', 'anthropic')),
    account_id         TEXT        NOT NULL,
    usage_date         DATE        NOT NULL,
    model              TEXT        NOT NULL,
    workspace          TEXT        NOT NULL DEFAULT '',
    api_key_id         TEXT        NOT NULL DEFAULT '',
    caller             TEXT        NOT NULL DEFAULT '',
    application        TEXT        NOT NULL DEFAULT '',
    input_tokens       BIGINT      NOT NULL CHECK (input_tokens >= 0),
    output_tokens      BIGINT      NOT NULL CHECK (output_tokens >= 0),
    cache_read_tokens  BIGINT      NOT NULL CHECK (cache_read_tokens >= 0),
    cache_write_tokens BIGINT      NOT NULL CHECK (cache_write_tokens >= 0),
    requests           BIGINT      CHECK (requests >= 0),
    as_of              TIMESTAMPTZ NOT NULL,
    collected_at       TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, provider, account_id, usage_date, model,
                 workspace, api_key_id, caller, application)
);

-- TASK-P13-004
CREATE TABLE ai_provider_account (
    provider         TEXT        NOT NULL CHECK (provider IN ('openai', 'anthropic')),
    organization_id  TEXT        NOT NULL,
    tenant_id        UUID        NOT NULL REFERENCES tenant(tenant_id),
    name             TEXT        NOT NULL,
    key_secret_name  TEXT        NOT NULL CHECK (key_secret_name LIKE 'meter/%/ai/%'),
    enrolled_at      TIMESTAMPTZ NOT NULL,
    active           BOOLEAN     NOT NULL DEFAULT true,
    PRIMARY KEY (provider, organization_id)
);

-- TASK-P13-006
CREATE TABLE gpu_utilization_daily (
    tenant_id        UUID          NOT NULL REFERENCES tenant(tenant_id),
    ingest_run_id    UUID          NOT NULL,
    account_id       TEXT          NOT NULL,
    region_id        TEXT          NOT NULL,
    instance_id      TEXT          NOT NULL,
    usage_date       DATE          NOT NULL,
    gpu_count        INTEGER       NOT NULL CHECK (gpu_count > 0),
    average_percent  NUMERIC(5, 2) NOT NULL CHECK (average_percent BETWEEN 0 AND 100),
    peak_percent     NUMERIC(5, 2) NOT NULL CHECK (peak_percent BETWEEN 0 AND 100),
    samples          INTEGER       NOT NULL CHECK (samples > 0),
    as_of            TIMESTAMPTZ   NOT NULL,
    collected_at     TIMESTAMPTZ   NOT NULL,
    PRIMARY KEY (tenant_id, account_id, region_id, instance_id, usage_date),
    CONSTRAINT ck_gpu_utilization_daily__peak_at_least_average
        CHECK (peak_percent >= average_percent)
);
```

`ai_usage_daily.caller` holds an IAM ARN or a provider user identifier, which can name a person,
so it is class P in `docs/09-DATA-CLASSIFICATION.md` with the same retention as the CloudTrail
creators of P11.

## 7. Collectors and cadence

| Collector | Unit | Cadence | Reads | Cost, modelled |
| --- | --- | --- | --- | --- |
| `cost_focus` | billing | unchanged | the bill, now with its AI columns | unchanged |
| `bedrock_invocations` | account and Region | daily | the day before, from Logs Insights | USD 0.005 per GB scanned at the list price, borne by the member account |
| `openai_usage` | provider organization | daily | cost and usage, the period to date | none, the reports are not billed |
| `anthropic_usage` | provider organization | daily | cost and usage, the period to date | none, the reports are not billed |
| `gpu_utilization` | account and Region | daily | the day before, CloudWatch | USD 0.01 per 1,000 metrics requested at the list price |

Each is a row of `collector_schedule` with its reason and its cost, constraint 9, and a binding in
both compositions, P12. A provider run rereads the billing period to date because both providers
revise recent buckets; its delete removes what the provider withdrew, keyed on its source and
organization.

## 8. Interface

- `GET /v1/ai/spend`: AI cost for a period, grouped by provider, model, token type, feature or
  caller, with tokens, requests, cost per thousand tokens and per request, each with its basis.
- `GET /v1/ai/callers`: tokens, requests and modelled cost per caller and application.
- `GET /v1/ai/gpu`: each GPU instance's hours and cost, with utilization or not published.
- An AI spend screen in the web interface, reached from the navigation.
- `scripts/ops/connect_ai_provider.py`, which records a provider organization for a tenant after
  one cheap read with its key succeeds, and `make first-contact` probes for every new read.

Every response carries `as_of` and `collected_at`, constraint 10.

## 9. Testing

The usage type parser is tested against every suffix AWS documents and against unrecognised ones.
The bill mapping is tested with an export fixture carrying Bedrock line items, and without the
optional columns. The provider adapters are tested against recorded response shapes through an
httpx mock transport, for every typed failure. The invocation logs adapter is tested under moto
where moto covers it and a stub where it does not, and its query is held to aggregates. The
restatement deletes are tested so that an AWS run leaves a provider's rows and the reverse. The
Terraform is read by a test that fails if any security group other than the worker's egresses to
the internet. The screen has unit tests and a Playwright journey on the seeded demo.

## 10. Risks

- Every mapping here is checkable only against a real export or a real key, ISS-002 and ISS-285.
  The Bedrock suffixes come from AWS's documentation, and a usage type that does not match leaves
  the AI columns null, so the cost still counts and only the breakdown is missing.
- The NAT gateway gives the worker a route to the whole internet on 443. Only the worker has it,
  the flow logs record every connection, and ADR-0036 states the trade.
- Invocation logs hold prompts. Meter's query is held to aggregates by a test and the role's reach
  to a log group pattern the owner sets, and a person who can change the collector's code could
  still change the query, which is why the test is in the gate.
- Logs Insights bills the bytes it scans, in the member account. A busy account's logs can be large
  because they hold the bodies, so the cost is modelled per GB and shown with the collector.
- During a rolling deploy, an old cost task's delete ignores `ingest_source` and can remove a
  provider's rows until the provider's next run, at most one day.

## 11. Open questions

- OPEN-31: how a deployed Meter reaches OpenAI and Anthropic. Answered 2026-10-12, a NAT gateway.
- OPEN-32: where Bedrock cost per user and agent comes from. Answered 2026-10-12, invocation logs
  where enabled.
- OPEN-33: what GPU spend shows. Answered 2026-10-12, utilization as well as hours and cost.
- OPEN-34: how token fields are stored before FOCUS 1.5. Answered 2026-10-12, `x_` columns now.

## 12. Features delivered

- FEAT-081: Bedrock cost by model, token type, application and IAM principal, from the bill.
- FEAT-082: Bedrock usage per caller from invocation logs.
- FEAT-083: OpenAI and Anthropic cost and usage beside the AWS bill.
- FEAT-084: GPU hours, cost and utilization.
- FEAT-085: The AI spend screen: cost per token, per request and per feature.

## 13. Exit criteria

1. A Bedrock line item in the fake export lands with its model, token type, tokens and IAM
   principal, and the spend endpoint groups by each.
2. Where invocation logging reaches CloudWatch Logs, usage per caller lands from an aggregate query;
   where it does not, the account reads NotOptedIn.
3. OpenAI and Anthropic cost lands as FOCUS rows and survives an AWS cost run, and their usage lands
   per model, project or workspace, and key.
4. GPU instances show hours and cost, and utilization where published, not published otherwise.
5. Only the worker can reach the internet, held by a test of the Terraform.
6. The screen shows cost per token, per request and per feature, each labelled measured or
   modelled, on the local stack.
