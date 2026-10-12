# Runbook: AI spend sources

The owner's steps to give Meter each source of AI spend beyond the bill, each with the check that
says it worked. P13, FEAT-081 to FEAT-085, TASK-P13-009. The bill's own Bedrock and GPU lines need
nothing here: they arrive with the cost export. This file covers what the bill cannot say: an AI
provider's own cost and usage, who called a Bedrock model, and how busy a GPU was.

> **Nothing here has been done against a real source yet.** The OpenAI and Anthropic adapters are
> written to each provider's published reference and tested against recorded shapes, ISS-285, and
> no organization has given Meter a key. Expect the first run of each step to find something, and
> record it in `tasks/ISSUES.md` as it happens.

## An AI provider organization, OpenAI or Anthropic

Meter reads an organization's cost report and usage report with its admin key. An ordinary API key
cannot read either report. The worker reaches the provider through the NAT gateway only it may use,
ADR-0036, and reads the key from Secrets Manager when it is about to make a request; the key is never
printed, logged or stored anywhere else, and the database holds only the secret's name.

| # | Step | Check |
| --- | --- | --- |
| 1 | An owner or admin of the organization creates an admin key in the provider's console, named for Meter so it can be revoked on its own | The console lists the key |
| 2 | Store it in the hub account under the AI path, `meter/<env>/ai/`, from a file rather than the command line, so it stays out of the shell's history; delete the file afterwards | `aws secretsmanager describe-secret --secret-id meter/dev/ai/openai-platform` answers |
| 3 | First contact with the key, below | The provider's line reads `answered` |
| 4 | Connect the organization to the tenant, below | The script prints `connected` and how many cost lines the key read |
| 5 | Wait for the next run of `openai_usage` or `anthropic_usage`, daily | The AI spend screen, under Analyze, lists the organization under Connected, and Data Freshness shows the collector |

Step 2, with the key in `key.txt`:

```bash
aws secretsmanager create-secret --name meter/dev/ai/openai-platform --secret-string file://key.txt
```

Step 3, with credentials for the hub account and `AWS_REGION` set to the hub's Region:

```bash
make first-contact ENV=dev ACCOUNT=<a member account id> REGION=<a Region it uses> OPENAI_SECRET=meter/dev/ai/openai-platform
```

`ANTHROPIC_SECRET=` reads an Anthropic organization the same way. A provider whose secret is not
named is not read, and the report says so, so an estate without one still answers every read.

Step 4, with the database the tasks use:

```bash
METER_DATABASE_URL=<the database URL> AWS_REGION=<the hub Region> python scripts/ops/connect_ai_provider.py --env dev --tenant <tenant uuid> --provider openai --organization <the organization id> --name "Platform team" --secret meter/dev/ai/openai-platform
```

It reads one day of costs with the key before it records anything, so a row exists only for an
organization whose key was proved. It exits 0 when connected, 2 when an argument or a setting is
wrong or another tenant already holds the organization, and 3 when the key could not be read or the
provider refused it, with the typed cause.

| What the check says | What it means | What to do |
| --- | --- | --- |
| `Misconfigured`, not under the AI path | The secret's name does not start `meter/<env>/ai/` | Store it under that path; the task role may read nothing else |
| `Misconfigured`, no secret named | The secret does not exist in the hub account and Region | Step 2 in the hub account |
| `AccessDenied` | The key was revoked, or it is not an admin key | A new admin key, step 1 |
| `Throttled` | The provider limited the request rate | Nothing; the next run retries |
| `SchemaDrift` | The provider answered in a shape the adapter does not know, ISS-285 | Record it with the field it names; never read it as zero |

**Rotating a key.** Put the new key in the same secret. Nothing else changes, because the worker
reads the secret at each request.

**Disconnecting.** Not scripted yet. Revoking the key stops the reads, and each run then records
`AccessDenied` against the organization, which Data Freshness shows rather than a zero.

## Who called a Bedrock model: invocation logging

The bill names the IAM principal, usually a role. The invocation logs name the caller and, when an
application attaches it, the request metadata it names itself under. They also carry the prompt and
the response, so Meter reads them only through a CloudWatch Logs Insights query whose every output
is a sum: requests and the four token counts by caller, model and, where set, the metadata key's
value. A test holds the query to aggregates and fails if it names a body field.

| # | Step | Check |
| --- | --- | --- |
| 1 | In each member account and Region that uses Bedrock, turn on model invocation logging with CloudWatch Logs as a destination. Logs delivered to S3 alone cannot be read and the account reads `NotOptedIn` | `aws bedrock get-model-invocation-logging-configuration` names a `cloudWatchConfig` log group |
| 2 | The log group must match the member StackSet parameter `InvocationLogGroupPattern`, default `/aws/bedrock/*`. The collector role may start a query on no other group | The log group's name, against the parameter |
| 3 | Optional: name the request metadata key your applications use, `METER_AI_REQUEST_METADATA_KEY`, so usage is grouped by application as well as caller | The setting in the environment's tfvars |
| 4 | First contact | `Bedrock's invocation logging configuration` reads `answered` |
| 5 | Wait for the next `bedrock_invocations` run, daily, for the day before | The AI spend screen's callers panel lists the account's callers |

Each daily query scans that day's log data, and Logs Insights charges per gigabyte scanned at AWS's
published price (modelled); a busy account's logs make that the largest cost of this source. Whether
the logs carry prompt text is the account's own choice, made in the same setting, and Meter never
reads it either way.

## How busy a GPU was: the CloudWatch agent

GPU hours and cost come from the bill. Utilization comes from the CloudWatch agent on the instance,
which publishes `nvidia_smi_utilization_gpu` when its NVIDIA GPU metrics are turned on. An instance
without it shows **not published** on the screen, never nought percent.

| # | Step | Check |
| --- | --- | --- |
| 1 | Install the CloudWatch agent on each GPU instance with its NVIDIA GPU metrics on | The instance's metrics appear in the agent's namespace |
| 2 | If the agent publishes somewhere other than `CWAgent`, set `METER_GPU_METRICS_NAMESPACE` to that namespace | The setting in the environment's tfvars |
| 3 | First contact | `the GPU agent's metrics` reads `answered` |
| 4 | Wait for the next `gpu_utilization` run, daily, for the day before | The GPU panel shows the instance's average and peak, and how many billed days its agent covered |

The collector asks only about the GPU instances the bill names in each account and Region, so an
instance nobody paid for is never asked about and the role needs no new permission.

## On the local stack

`make seed` lays down every source with fakes: the bill's Bedrock and GPU lines, a connected fake
OpenAI and a fake Anthropic organization, invocation logs in one account and `NotOptedIn` in
another, and two GPU instances, one publishing and one not. Nothing in it talks to a provider or to
AWS; see [demo.md](demo.md).
