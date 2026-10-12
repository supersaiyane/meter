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
| Status | Not started |
| Implements | Spec section 5.1, OPEN-31, ADR-0036 |
| Delivers | FEAT-083 |
| Depends on | Nothing |
| Estimate | S |

**Acceptance criteria.**

- [ ] One NAT gateway with an Elastic IP in the first public subnet, and a default route to it from
      the private route table, tagged like the rest of the hub
- [ ] The worker service has a security group of its own allowing TCP 443 to anywhere, and no other
      group egresses to the internet, held by a test of the Terraform
- [ ] `tests/contract/test_network_paths.py` holds the two provider hosts to the NAT path
- [ ] `docs/04-DEPLOYMENT.md` and `network.tf`'s header say what changed and why

---

### TASK-P13-002: the bill's AI columns

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec sections 5.2 and 5.3, OPEN-34 |
| Delivers | FEAT-081 |
| Depends on | Nothing |
| Estimate | M |

**Acceptance criteria.**

- [ ] A migration adds `ingest_source` and the five `x_` columns to `cost_focus_daily`, with their
      constraints, additive only
- [ ] A pure usage type parser in `finops_core` reads model and token type from every Bedrock
      suffix AWS documents, and returns nothing for a usage type it does not recognise
- [ ] `cur.py` reads `x_usagetype` and `line_item_iam_principal` where the catalog has them, and an
      export without them is read with the SQL it always was
- [ ] The cost collector writes the new columns and its restatement delete keys on `aws_export`
- [ ] The fake export carries Bedrock token line items

---

### TASK-P13-003: Bedrock usage per caller from invocation logs

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 5.4, OPEN-32 |
| Delivers | FEAT-082 |
| Depends on | TASK-P13-002 |
| Estimate | M |

**Acceptance criteria.**

- [ ] A migration creates `ai_usage_daily`
- [ ] An adapter reads each account and Region's invocation logging configuration and, where it
      names a CloudWatch log group, runs one aggregate Logs Insights query for the day before
- [ ] A test fails if the query names a body field or returns anything but aggregates
- [ ] No CloudWatch log group is NotOptedIn with the step that enables it
- [ ] The collector role gains the logging configuration read and a query start scoped to
      `InvocationLogGroupPattern`
- [ ] The collector is scheduled, composed in both modes and has a fake

---

### TASK-P13-004: provider accounts and OpenAI

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 5.5 |
| Delivers | FEAT-083 |
| Depends on | TASK-P13-001, TASK-P13-002, TASK-P13-003 |
| Estimate | M |

**Acceptance criteria.**

- [ ] A migration creates `ai_provider_account`, and `scripts/ops/connect_ai_provider.py` records an
      organization after one read with its key succeeds
- [ ] The worker's role may read secrets under `meter/<env>/ai/` and nothing else new
- [ ] An httpx adapter reads OpenAI's cost and usage reports, paginated, every failure typed
- [ ] The collector writes FOCUS rows with `ingest_source` openai and usage rows, and its delete
      removes only its own organization's withdrawn rows
- [ ] The key appears in no log, error or row, held by a test

---

### TASK-P13-005: Anthropic

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 5.5 |
| Delivers | FEAT-083 |
| Depends on | TASK-P13-004 |
| Estimate | M |

**Acceptance criteria.**

- [ ] An httpx adapter reads Anthropic's cost report and messages usage report, paginated, every
      failure typed
- [ ] The collector writes FOCUS rows with `ingest_source` anthropic and usage rows, the same way
- [ ] An AWS cost run leaves both providers' rows, and each provider's run leaves the bill's

---

### TASK-P13-006: GPU utilization

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 5.6, OPEN-33 |
| Delivers | FEAT-084 |
| Depends on | TASK-P13-002 |
| Estimate | M |

**Acceptance criteria.**

- [ ] A migration creates `gpu_utilization_daily`
- [ ] A query finds GPU instances in the bill with their hours and cost
- [ ] An adapter reads `nvidia_smi_utilization_gpu` for each EC2 GPU instance the bill names, in
      the namespace `gpu_metrics_namespace` names, and an instance that publishes nothing has no row
- [ ] The collector is scheduled, composed in both modes and has a fake

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
