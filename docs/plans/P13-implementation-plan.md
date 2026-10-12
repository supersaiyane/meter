# P13 FinOps for AI: implementation plan

Date: 2026-10-12
Status: Approved by the owner on 2026-10-12 with OPEN-31 to OPEN-34 answered, in build
Spec: `docs/specs/2026-10-12-p13-finops-for-ai-design.md`
Depends on: P1, P3 and P12. Proof against a real estate waits on ISS-002 and ISS-285
Tasks: 9

Meter reads a Bedrock charge as a cost row like any other and never sees the OpenAI or Anthropic
bill at all. This sub project reads the AI fields in the bill, Bedrock usage per caller from
invocation logs, the two providers' cost and usage through a NAT gateway only the worker can use,
and GPU utilization, and shows cost per token, per request and per feature on one screen.

## How to work this plan

Same contract as P0 through P12. One task, one commit, `make verify` green before a merge.

**Three rules specific to P13.**

1. **Never a prompt or a response.** Nothing Meter runs reads a body from an invocation log, and a
   test fails the gate if the query names one.
2. **No key outside Secrets Manager.** A provider admin key is read at run time from
   `meter/<env>/ai/`, and never reaches a setting, a log, an error or the database.
3. **Each source restates its own rows.** A delete that removes withdrawn rows keys on its source,
   so no collector removes another's.

## Wave overview

| Wave | Tasks | Delivers | Can start when |
| --- | --- | --- | --- |
| A. The path and the columns | 001, 002 | The worker's route out, the bill's AI fields | This plan approved |
| B. The sources | 003, 004, 005, 006 | Invocation logs, OpenAI, Anthropic, GPU utilization | A |
| C. The screen | 007, 008 | The endpoints and the AI spend screen | B |
| D. Proof and documents | 009 | The local stack, first contact, exit criteria | All |

Modelled at the pace of P12: seven tasks of size M and two of size S, about eight working days.

---

### TASK-P13-001: the NAT gateway, for the worker only

| Field | Value |
| --- | --- |
| Status | Done 2026-10-12 |
| Implements | Spec section 5.1, OPEN-31, ADR-0036 |
| Delivers | FEAT-083 |
| Depends on | Nothing |
| Estimate | S |

**Acceptance criteria.**

- [x] One NAT gateway with an Elastic IP in the first public subnet, and a default route to it from
      the private route table, tagged `finops:module = ai`
- [x] The worker service has a security group of its own allowing TCP 443 to anywhere, and no other
      group egresses to the internet, held by a test of the Terraform
- [x] `tests/contract/test_network_paths.py` holds the two provider hosts to the NAT path
- [x] `docs/04-DEPLOYMENT.md` and `network.tf`'s header say what changed and why

**Delivered 2026-10-12.** `infra/terraform/hub/network.tf` adds `aws_eip.nat`,
`aws_nat_gateway.providers` in `aws_subnet.public[0]` and `aws_route.to_the_providers`; `alb.tf` adds
`worker_internet` with its one rule, TCP 443 to `0.0.0.0/0`, and `ecs.tf` gives it to the worker
service alone. `tests/contract/test_network_paths.py` replaces its two tests that there is no NAT with
four: one gateway, the worker's, in a public subnet; the private route table's three routes; one
egress rule to the internet in the whole hub, the worker's on 443; and the worker service the only
one carrying the group. A fifth reads every string in the production code and fails on a host
outside AWS that is not one of the two providers', so a new host is a failed test. Nothing applied,
ISS-002.

---

### TASK-P13-002: the bill's AI columns

| Field | Value |
| --- | --- |
| Status | Done 2026-10-12 |
| Implements | Spec sections 5.2 and 5.3, OPEN-34 |
| Delivers | FEAT-081 |
| Depends on | Nothing |
| Estimate | M |

**Acceptance criteria.**

- [x] A migration adds `ingest_source` and the five `x_` columns to `cost_focus_daily`, with their
      constraints, additive only
- [x] A pure usage type parser reads model and token type from every Bedrock
      suffix AWS documents, and returns nothing for a usage type it does not recognise
- [x] `cur.py` reads `x_usagetype` and `line_item_iam_principal` where the catalog has them, and an
      export without them is read with the SQL it always was
- [x] The cost collector writes the new columns and its restatement delete keys on `aws_export`
- [x] The fake export carries Bedrock token line items

**Delivered 2026-10-12.** Migration `0047_cost_ai_columns`; the parser in
`finops_providers/aws/bedrock_usage.py`, applied by the export as it reads a row, and not in
`finops_core`, because ADR-0028's test keeps every vendor's name out of that package; the token
types alone are in `finops_core/domain/ai.py`; `AI_COLUMNS` in
`finops_providers/aws/cur.py`; and the cost collector's restatement keyed on `ingest_source`, with a
row from another source refused. The fake export's two Bedrock features are opt in, `ai=True`, so no
earlier figure moves; the demo and the local stack take them in TASK-P13-009, with the journeys.
Tests: `tests/core/test_ai.py`, `TestAiColumns` in `tests/providers/aws/test_cur.py`, and
`tests/ingest/collectors/test_cost_focus_sources.py`, which proves a provider's row survives the
bill's restatement and the table refuses each broken combination of the token columns.

---

### TASK-P13-003: Bedrock usage per caller from invocation logs

| Field | Value |
| --- | --- |
| Status | Done 2026-10-12 |
| Implements | Spec section 5.4, OPEN-32 |
| Delivers | FEAT-082 |
| Depends on | TASK-P13-002 |
| Estimate | M |

**Acceptance criteria.**

- [x] A migration creates `ai_usage_daily`
- [x] An adapter reads each account and Region's invocation logging configuration and, where it
      names a CloudWatch log group, runs one aggregate Logs Insights query for the day before
- [x] A test fails if the query names a body field or returns anything but aggregates
- [x] No CloudWatch log group is NotOptedIn with the step that enables it
- [x] The collector role gains the logging configuration read and a query start scoped to
      `InvocationLogGroupPattern`
- [x] The collector is scheduled, composed in both modes and has a fake

**Delivered 2026-10-12.** Migration `0048_ai_usage_daily`; the `InvocationLogs` port in a new
`AI_PORTS` group; `finops_providers/aws/bedrock_invocations.py`, which reads the logging
configuration and runs one Logs Insights `stats` query a day, every page of its answer;
`finops_ingest/collectors/ai_usage.py`, whose writer and restatement TASK-P13-004 and 005 share;
`FakeInvocationLogs` with the three cases, read, S3 only and nowhere; the schedule entry, both
compositions, and `retention_ai_usage` at 13 months. The role gains the configuration read and
`logs:GetQueryResults`, and `logs:StartQuery` only on `InvocationLogGroupPattern`;
`tests/contract/test_no_llm_writes.py` names StartQuery as a read, which IAM classes it as, and
StopQuery is not granted. The hub gains a Bedrock endpoint in each collection Region, as ADR-0035
requires, modelled at 16.06 USD a month each. The setting is `ai_request_metadata_key`, ADR-0028.

---

### TASK-P13-004: provider accounts and OpenAI

| Field | Value |
| --- | --- |
| Status | Done 2026-10-12 |
| Implements | Spec section 5.5 |
| Delivers | FEAT-083 |
| Depends on | TASK-P13-001, TASK-P13-002, TASK-P13-003 |
| Estimate | M |

**Acceptance criteria.**

- [x] A migration creates `ai_provider_account`, and `scripts/ops/connect_ai_provider.py` records an
      organization after one read with its key succeeds
- [x] The task role may read secrets under `meter/<env>/ai/` and nothing else new; it is shared
      with the API, ISS-286
- [x] An httpx adapter reads OpenAI's cost and usage reports, paginated, every failure typed
- [x] The collector writes FOCUS rows with `ingest_source` openai and usage rows, and its delete
      removes only its own organization's withdrawn rows
- [x] The key appears in no log, error or row, held by a test

**Delivered 2026-10-12.** Migration `0049_ai_provider_account`; the `AiProviderReports` port;
`finops_providers/ai_reports.py`, the paged client both providers share, retries bounded and every
failure typed, a refused key's message never kept; `finops_providers/openai/reports.py`;
`finops_providers/aws/secrets.py`, which refuses a name outside the AI path before any call;
`finops_ingest/collectors/ai_providers.py`, one organization failing typed under its own scope
and never failing another, with the cost writer and the per organization restatement now shared
in `cost_focus.py`; `openai_usage` in both compositions; and the connect script. Migration
`0050_ai_collector_schedules` installs the new collectors' cadences for existing tenants, and
found `retention_assistant` had none, ISS-287, fixed by the same migration. The task role is
shared with the API, ISS-286.

---

### TASK-P13-005: Anthropic

| Field | Value |
| --- | --- |
| Status | Done 2026-10-13 |
| Implements | Spec section 5.5 |
| Delivers | FEAT-083 |
| Depends on | TASK-P13-004 |
| Estimate | M |

**Acceptance criteria.**

- [x] An httpx adapter reads Anthropic's cost report and messages usage report, paginated, every
      failure typed
- [x] The collector writes FOCUS rows with `ingest_source` anthropic and usage rows, the same way
- [x] An AWS cost run leaves both providers' rows, and each provider's run leaves the bill's

**Delivered 2026-10-13.** `finops_providers/anthropic/reports.py`: the cost report's amounts are in
cents and are divided by a hundred, its model and token type are fields of their own rather than
read out of the description, and the messages usage report counts no requests, so a row's
`requests` is None and never a zero. The default workspace, which the report names with no id,
reads as the empty workspace. `anthropic_usage` in both compositions over the shared provider
collector; the connect script takes `--provider anthropic`; migration `0051_anthropic_schedule`
installs its cadence for existing tenants. A test runs the bill, OpenAI and Anthropic into one
period and finds each source's rows intact after the others' runs.

---

### TASK-P13-006: GPU utilization

| Field | Value |
| --- | --- |
| Status | Done 2026-10-13 |
| Implements | Spec section 5.6, OPEN-33 |
| Delivers | FEAT-084 |
| Depends on | TASK-P13-002 |
| Estimate | M |

**Acceptance criteria.**

- [x] A migration creates `gpu_utilization_daily`
- [x] The collector finds GPU instances in the bill; their hours and cost on the screen are
      TASK-P13-007's query
- [x] An adapter reads `nvidia_smi_utilization_gpu` for each EC2 GPU instance the bill names, in
      the namespace `gpu_metrics_namespace` names, and an instance that publishes nothing has no row
- [x] The collector is scheduled, composed in both modes and has a fake

**Delivered 2026-10-13.** Migration `0052_gpu_utilization_daily`, with the collector's cadence for
existing tenants; `accelerated_instance_type` and `GpuUtilization` in `finops_core/domain/ai.py`;
the `GpuMetrics` port; `finops_providers/aws/gpu_metrics.py`, which lists each instance's
accelerator metrics before reading them, because the dimensions besides the instance are not known
in advance, and gives the instance the mean of its accelerators' averages and the highest peak;
`finops_ingest/collectors/gpu_utilization.py`, which asks only about the accelerated instances the
bill names, so it needs no permission the role did not have; the `METER_GPU_METRICS_NAMESPACE`
setting; a fake bill with two GPU instances, one publishing and one not; and both compositions.

---

### TASK-P13-007: the AI endpoints

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec sections 5.5, 5.7 and 8 |
| Delivers | FEAT-081, FEAT-082, FEAT-084 |
| Depends on | TASK-P13-002 to TASK-P13-006 |
| Estimate | M |

**Acceptance criteria.**

- [ ] `GET /v1/ai/spend`, `GET /v1/ai/callers` and `GET /v1/ai/gpu`, each through the scope
      dependency and the repository guard, each figure with its basis and both timestamps
- [ ] A provider row is visible at global scope only, held by a test
- [ ] Cost per thousand tokens and per request are measured where cost and count come from the
      same rows and modelled where they do not

---

### TASK-P13-008: the AI spend screen

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 8 |
| Delivers | FEAT-085 |
| Depends on | TASK-P13-007 |
| Estimate | M |

**Acceptance criteria.**

- [ ] A screen, reached from the navigation, shows AI spend by provider, model, token type, feature
      and caller, cost per thousand tokens and per request, and the GPU fleet
- [ ] Every figure says measured or modelled, every panel shows freshness, a failure is never zero,
      and not published reads as not published
- [ ] Unit tests and a Playwright journey on the seeded demo

---

### TASK-P13-009: the local stack, first contact, proof and documents

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 13 |
| Delivers | The exit criteria, measured, and the record |
| Depends on | TASK-P13-001 to TASK-P13-008 |
| Estimate | S |

**Acceptance criteria.**

- [ ] The seeded demo and the local stack carry AI spend from every source
- [ ] `make first-contact` probes each new read, and the runbook names the owner's steps for a
      provider key and for invocation logging
- [ ] Every exit criterion in spec section 13 met, each with its evidence
- [ ] FEAT-081 to FEAT-085 say what was built; the register, `project_map.md` and the checkpoint
      updated, and `make check-docs` clean
