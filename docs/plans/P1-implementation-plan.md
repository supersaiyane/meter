# P1 Cost Intelligence: implementation plan

Date: 2026-09-18
Status: Provisional, pending approval of `docs/specs/2026-09-18-p1-cost-intelligence-design.md`
Spec: `docs/specs/2026-09-18-p1-cost-intelligence-design.md`
Depends on: P0 delivered
Tasks: 13

This plan covers the **cost surface** only. Section 3 of the spec names what P1
leaves for a second cut and why.

## How to work this plan

Same contract as P0 and P2. Read `docs/03-CHANGE-CONTROL.md`, section "The anti
hallucination contract", before starting.

One task, one commit. Read the **Deliberately not in this task** list before
writing code, not after. If reality does not match the spec, stop, raise an
`ISS-nnn`, fix the spec, add a `CHG-nnnn`, then continue.

**Three rules specific to P1.**

1. **There is no AWS account.** ISS-122. Every task below is built and proved
   against `FakeCostExport`. TASK-P1-003 writes the Athena adapter and cannot
   prove it, and says so in its own acceptance criteria rather than claiming a
   green test means a working integration.

2. **The schema is already there.** P0 migrated `cost_focus_daily`,
   `cost_focus_monthly` and `cost_provider_extra`. No task here adds a
   migration. A task that finds it needs one has found a disagreement with the
   spec and should stop at the disagreement.

3. **The guard entry goes in before the route.** TASK-P2-021 wrote six routes
   over six tables that were not in `SCOPED_TABLES`, and every one returned 500
   on its first real call while importing cleanly and passing its tests.
   TASK-P1-008 does the guard, and TASK-P1-009 does not start until a test has
   read out of scope and been refused.

## Wave overview

| Wave | Tasks | Delivers | Can start when |
| --- | --- | --- | --- |
| A. Port and adapters | 001 to 003 | `CostExport`, a fake estate with a bill, and an unproved Athena adapter | P0 delivered |
| B. Ingest | 004 to 007 | FOCUS rows in the database, idempotent under restatement, rolled up and scheduled | A |
| C. Surface | 008 to 009 | The guard, the repository and four routes | B |
| D. Screens | 010 to 012 | Two screens, a seeded bill and a journey | C |
| E. Infrastructure | 013 | Terraform that validates and is not applied | A |

Wave E does not depend on B, C or D. It can be done at any point and is last
because it cannot be proved.

---

### TASK-P1-001: the cost port and the types that carry a measure

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P1 spec sections 4 and 5 |
| Delivers | FEAT-020 |
| Depends on | none |
| Estimate | S |

**Goal.** The port every cost adapter implements, and the domain types that
stop a number travelling without saying what it measures.

`CostRecord` already exists. This adds `BillingPeriod`, which knows whether it
is open, and `CostTotal`, which carries its measure. A screen rendering
amortized cost under a label saying billed is a defect nobody can see by
reading it, and a type is the only thing that catches it.

**Files.**

| Path | Action |
| --- | --- |
| `finops_core/ports/cost.py` | created, `CostExport` with `periods()` and `rows(period)` |
| `finops_core/domain/cost.py` | extended, `BillingPeriod` and `CostTotal` |
| `tests/core/test_cost_domain.py` | created |

**Acceptance criteria.**

- [ ] `finops_core` still imports no boto3, no framework and no HTTP client,
      which import-linter already enforces
- [ ] A `CostTotal` cannot be constructed without a measure
- [ ] `BillingPeriod.is_open` is derived from the period's end against a clock
      passed in, never from `datetime.now()` inside the type

**Deliberately not in this task.** No adapter, no collector. A port with two
implementations and no caller is the right amount of nothing to have built.

---

### TASK-P1-002: a fake estate with a bill

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P1 spec sections 4 and 11 |
| Delivers | FEAT-020 |
| Depends on | TASK-P1-001 |
| Estimate | M |

**Goal.** `FakeCostExport`, producing FOCUS 1.1 rows for a synthetic estate,
with a configurable failure, the same pattern `FakeQuerySurface` established.

The estate has to contain the states the screens exist to tell apart, or the
screens can look finished while rendering one case. It needs more than one
account, more than one service, a resource level row and a row with no
`resource_id`, tagged rows and untagged rows so the unallocated bucket is not
empty, an open period and a closed one, and a period that can be restated on
demand so TASK-P1-005 has something to restate.

**Files.**

| Path | Action |
| --- | --- |
| `finops_providers/fake/cur.py` | created |
| `tests/providers/fake/test_cur.py` | created |

**Acceptance criteria.**

- [ ] Every row is valid FOCUS 1.1 and passes the same normalization the AWS
      adapter's output does
- [ ] The estate contains an untagged row, so the unallocated bucket has
      something in it before anybody writes the screen
- [ ] A restatement can be asked for: one row changed, one row retracted
- [ ] A failure can be asked for, by typed cause, and is raised rather than
      returned

**Deliberately not in this task.** No random data. A fake whose numbers move
between runs cannot be asserted against, and this project has already been
caught by a green test that measured nothing.

---

### TASK-P1-003: the Athena adapter, written and unproved

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P1 spec sections 4, 7 and 10 |
| Delivers | FEAT-020 |
| Depends on | TASK-P1-001 |
| Estimate | M |

**Goal.** `AthenaCostExport`. Reads the Data Exports manifest from S3, runs one
partition pruned query per billing period, pages the results, normalizes to
FOCUS.

**Files.**

| Path | Action |
| --- | --- |
| `finops_providers/aws/cur.py` | created |
| `tests/providers/aws/test_cur.py` | created, against recorded shapes |
| `tests/contract/test_cost_export.py` | created, runs against both adapters |

**Acceptance criteria.**

- [ ] The contract test passes against the fake and the AWS adapter, so the
      fake cannot drift into agreeing with a shape that does not exist
- [ ] `Throttled` is retried with backoff, and a period that is still throttled
      after the retries is returned as incomplete rather than as short
- [ ] The query prunes on the billing period partition. A full scan of a CUR
      table is the tool that reports on cost becoming a line on the bill
- [ ] **This adapter has never made a call.** The task is done when the code is
      written and unit tested, and the acceptance criterion is that the
      document says so, not that a test passed. ISS-122

**Deliberately not in this task.** No credentials work. The hub role already
reaches the payer, and inventing a second path to it now would be a second
thing to unpick when an account arrives.

---

### TASK-P1-004: the collector, and what makes a line item itself

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P1 spec sections 5 and 7 |
| Delivers | FEAT-020, FEAT-021 |
| Depends on | TASK-P1-002 |
| Estimate | L |

**Goal.** Read a period, normalize each row to FOCUS 1.1, compute
`source_fingerprint`, upsert `cost_focus_daily`, all through the run ledger.

The fingerprint is a hash of the columns that identify the charge and never of
the columns that state its size. Hashing the cost makes a restated row a new
row, which is the exact failure the primary key exists to prevent.

**Files.**

| Path | Action |
| --- | --- |
| `finops_ingest/collectors/cost_focus.py` | created |
| `finops_ingest/registry.py` | the collector registered |
| `tests/ingest/test_cost_focus.py` | created |

**Acceptance criteria.**

- [ ] Ingesting a period twice leaves exactly the same rows, proved by counting
      them and comparing, not by arguing that an upsert is idempotent
- [ ] A row whose cost changed updates in place and does not duplicate
- [ ] The fingerprint is stable across process restarts, which rules out
      `hash()`
- [ ] A missing partition fails the run rather than misfiling the cost, which
      `partitions.py` already does and this must not work around
- [ ] One account failing does not fail the run, and the cause is typed

**Deliberately not in this task.** No delete. Retraction is TASK-P1-005 and is
the only destructive operation in the ingest path, so it gets its own commit
and its own review.

---

### TASK-P1-005: retraction, which is the dangerous half

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P1 spec section 5 |
| Delivers | FEAT-020 |
| Depends on | TASK-P1-004 |
| Estimate | M |

**Goal.** When AWS retracts a line item, remove it. When the read failed part
way, remove nothing.

A period half read looks exactly like a period half retracted. A collector that
cannot tell those apart will delete a real bill the first time Athena throttles,
and the deletion will look like a successful run.

**Files.**

| Path | Action |
| --- | --- |
| `finops_ingest/collectors/cost_focus.py` | the complete period delete |
| `tests/ingest/test_cost_focus_restatement.py` | created |

**Acceptance criteria.**

- [ ] A restated period drops the retracted row and keeps the rest
- [ ] A run that failed part way deletes nothing, proved by failing the read
      after the first page and asserting the row count is unchanged
- [ ] The delete is keyed on `ingest_run_id` not on a timestamp, because two
      runs in the same second are not distinguishable by a clock
- [ ] The test that proves criterion 2 is watched failing with the guard
      removed before it is trusted

**Deliberately not in this task.** No soft delete and no retraction history. A
retracted charge is not a fact about the estate, it is a correction to a record
of one, and keeping both invites a screen that adds them together.

---

### TASK-P1-006: the monthly rollup, derived and never ingested

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P1 spec section 5 |
| Delivers | FEAT-021 |
| Depends on | TASK-P1-004 |
| Estimate | S |

**Goal.** `cost_focus_monthly`, computed from daily inside the same transaction
that writes daily.

Two sources for one number is how the two come to disagree, and the
disagreement is always found by a person reading a screen rather than by a test.

**Files.**

| Path | Action |
| --- | --- |
| `finops_ingest/collectors/cost_focus.py` | the rollup |
| `tests/ingest/test_cost_focus_rollup.py` | created |

**Acceptance criteria.**

- [ ] The monthly total equals the sum of the daily rows for that month, proved
      by a test that sums both and compares
- [ ] A retraction in TASK-P1-005 moves the monthly figure in the same
      transaction, so the two are never briefly inconsistent
- [ ] Rolling up twice changes nothing

**Deliberately not in this task.** No further rollups. A weekly or quarterly
table is a third source for the same number, and nothing has asked for one.

---

### TASK-P1-007: cadence, as data

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P1 spec section 7, ADR-0012 |
| Delivers | FEAT-020 |
| Depends on | TASK-P1-004 |
| Estimate | S |

**Goal.** The collector's intervals in `collector_schedule` with their reason
and their cost, per constraint 9. The open period is re read several times a
day because it is changing. A closed period is re read daily for a week, then
weekly.

**Files.**

| Path | Action |
| --- | --- |
| `finops_ingest/schedule.py` | the default rows |
| `tests/ingest/test_cost_schedule.py` | created |

**Acceptance criteria.**

- [ ] The intervals are rows, not constants in code
- [ ] `install_default_schedule` never overwrites an operator's change, which it
      already does not and this must not break
- [ ] Freshness on `/cost` is judged against this cadence and not a fixed
      number, which is how every other collector is judged

**Deliberately not in this task.** OPEN-08 is not answered here. Whether a
month is ever declared final is a decision, and this task ships the cadence the
decision would change.

---

### TASK-P1-008: the guard, then the repository

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P1 spec section 8, constraint 3 |
| Delivers | FEAT-021 |
| Depends on | TASK-P1-006 |
| Estimate | M |

**Goal.** `cost_focus_daily` and `cost_focus_monthly` in `SCOPED_TABLES` as
`ByAccount` on `sub_account_id`, and then a repository that cannot express an
unscoped read.

The guard comes first in this task, not after it. See rule 3 at the top of this
plan.

**Files.**

| Path | Action |
| --- | --- |
| `finops_api/guards.py` | two entries |
| `finops_api/db/repositories/cost.py` | created |
| `tests/db/test_scope_guard.py` | extended |
| `tests/api/test_cost_repository.py` | created |

**Acceptance criteria.**

- [ ] A narrow scope reads fewer rows than a global one, proved by a test that
      does both
- [ ] An empty scope returns nothing and never everything
- [ ] Every read writes an `audit_event` in the same transaction, as every other
      repository does
- [ ] The latest period filter is per period and not one global maximum, which
      is ISS-175 and ISS-177 arriving on a third table if nobody looks

**Deliberately not in this task.** No routes. The repository is provable on its
own and the route is where the scope dependency is added.

---

### TASK-P1-009: four routes

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P1 spec section 8 |
| Delivers | FEAT-021, FEAT-022 |
| Depends on | TASK-P1-008 |
| Estimate | M |

**Goal.** `GET /cost/summary`, `/cost/by-service`, `/cost/by-account` and
`/cost/trend`, all returning the meta envelope.

**Files.**

| Path | Action |
| --- | --- |
| `finops_api/routes/cost.py` | created |
| `finops_api/schemas.py` | the response models |
| `tests/api/test_cost_routes.py` | created |

**Acceptance criteria.**

- [ ] **Every route has been called**, not imported. A test that imports a
      route proves nothing, which is the standing lesson in `tasks/lessons.md`
- [ ] The envelope carries `as_of` and `collected_at` on every figure
- [ ] An open period is flagged as open in the payload, not inferred by the
      frontend from a date
- [ ] A typed collection failure reaches the envelope's trust strip by the same
      path an unreachable workspace does
- [ ] Scope is enforced twice, and a route with its dependency removed still
      cannot read out of scope

**Deliberately not in this task.** No allocation route. Allocation is a
grouping of these rows by a tag key, and a fifth route would be a second
implementation of one query.

---

### TASK-P1-010: the spend and trend screen

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P1 spec section 9 |
| Delivers | FEAT-021 |
| Depends on | TASK-P1-009 |
| Estimate | M |

**Goal.** `/cost`. The period total, the change against the previous period, a
daily trend, and the services that make it up.

**Files.**

| Path | Action |
| --- | --- |
| `finops-web/src/screens/CostScreen.tsx` | created |
| `finops-web/src/api/queries.ts` | the hooks |
| `finops-web/src/shell/sections.ts` | the placeholder replaced |
| `finops-web/src/screens/__tests__/CostScreen.test.tsx` | created |

**Acceptance criteria.**

- [ ] The open period is labelled as open beside the figure, not in a footnote.
      A reader comparing a part month against a whole month with no warning will
      reach a wrong conclusion confidently
- [ ] Every figure goes through `Figure`, so provenance and freshness are on the
      screen rather than in the payload
- [ ] A failed collection renders as a typed cause and never as zero,
      constraint 5
- [ ] ADR-0021 holds: `layout.css` targets no class a component had to add, and
      `surface.test.ts` still passes
- [ ] No accessibility violations, and the screen has been opened at 1440px and
      read

**Deliberately not in this task.** No per resource drill down. The rows are
stored and the screen for them is a separate decision.

---

### TASK-P1-011: the allocation screen and the bucket nobody wants

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P1 spec section 9 |
| Delivers | FEAT-022 |
| Depends on | TASK-P1-009 |
| Estimate | M |

**Goal.** `/cost/allocation`. Cost grouped by a tag key, with an explicit
`unallocated` row.

**Files.**

| Path | Action |
| --- | --- |
| `finops-web/src/screens/CostAllocationScreen.tsx` | created |
| `finops-web/src/shell/sections.ts` | the placeholder replaced |
| `finops-web/src/screens/__tests__/CostAllocationScreen.test.tsx` | created |

**Acceptance criteria.**

- [ ] The unallocated row is visible and is never folded into a total. An
      allocation view that quietly drops what it cannot attribute reports a
      smaller estate than exists
- [ ] Changing the tag key changes the grouping and not the total, proved by a
      test that sums both groupings and compares
- [ ] The same freshness, provenance and failure rules as TASK-P1-010

**Deliberately not in this task.** No Cost Categories. Tags first, and a second
allocation source before the first is proved makes a disagreement between them
impossible to attribute.

---

### TASK-P1-012: the demo estate gets a bill

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P1 spec sections 11 and 15 |
| Delivers | FEAT-021 |
| Depends on | TASK-P1-010, TASK-P1-011 |
| Estimate | S |

**Goal.** `make seed` writes cost through the real collector against the fake
adapter, as it does for every other collector, and one Playwright journey reads
the result.

**Files.**

| Path | Action |
| --- | --- |
| `scripts/ops/seed_demo.py` | the cost collector added, and the three cost tables added to `DEMO_TABLES` |
| `finops-web/e2e/cost.spec.ts` | created |
| `tests/scripts/test_seed_demo.py` | the teardown test already derives this |

**Acceptance criteria.**

- [ ] `make seed` fills `/cost` and `/cost/allocation`
- [ ] `make unseed` removes every cost row. The derived teardown test already
      fails if a tenant scoped table is missing from `DEMO_TABLES`, which is
      ISS-176 and is exactly this trap
- [ ] `make seed DAYS=n` produces a bill that differs by day, so the trend is a
      trend rather than one number drawn n times
- [ ] The journey opens `/cost`, reads a figure and follows it to
      `/cost/allocation`

**Deliberately not in this task.** No fake anomalies. There is no anomaly
screen to show them on.

---

### TASK-P1-013: the infrastructure that will not be applied

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P1 spec section 10 |
| Delivers | FEAT-020 |
| Depends on | TASK-P1-001 |
| Estimate | S |

**Goal.** The export bucket, the Glue catalog database and the Athena workgroup
in the hub stack.

**Files.**

| Path | Action |
| --- | --- |
| `infra/terraform/hub/cost_exports.tf` | created |
| `infra/terraform/hub/variables.tf` | extended |

**Acceptance criteria.**

- [ ] `terraform validate` and `terraform fmt -check` pass, which is syntax,
      provider schema and references
- [ ] Every resource is tagged `finops:module`, per constraint 7
- [ ] The Athena workgroup has a bytes scanned cutoff, because the tool that
      reports on cost is a thing that can run away
- [ ] **Nothing has been planned and nothing has been applied.** ISS-122. The
      task is done when the stack validates, and the document says that is what
      done means here

**Deliberately not in this task.** No member account IAM. CUR is read from the
payer, which the hub role already reaches.
