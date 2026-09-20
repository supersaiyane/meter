# P1 Cost Intelligence: implementation plan

Date: 2026-09-18
Status: Provisional, pending approval of `docs/specs/2026-09-18-p1-cost-intelligence-design.md`
Spec: `docs/specs/2026-09-18-p1-cost-intelligence-design.md`
Depends on: P0 delivered
Tasks: 21

The **cost surface** is tasks 001 to 013 and is delivered. The **second cut** is
014 to 021, and it is what section 3 of the specification deferred: anomalies,
commitments and the export. Section 16 of the specification records what
changed about those decisions and why they are being built now.

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
| F. Anomalies | 014 to 015 | A day that does not look like the days before it | D |
| G. Commitments | 016 to 017 | What was committed, and how much of it was used | D |
| H. Export | 018 | The file finance actually opens | D |
| I. Demo | 019 to 021 | A seeded estate and a design pass across every screen | F, G, H |

Wave E does not depend on B, C or D. It can be done at any point and is last
because it cannot be proved.

---

### TASK-P1-001: the cost port and the types that carry a measure

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-18 |
| Implements | P1 spec sections 4 and 5 |
| Delivers | FEAT-020 |
| Depends on | none |
| Estimate | S |

**Goal.** The domain types that stop a number travelling without saying what it
measures, and a period that cannot be read off by one.

**The port was already there.** P0 wrote `finops_core/ports/cost.py` with
`latest_available_period()` and `read_period(start, end)`, and it is better
than what this plan proposed, so it is unchanged. ISS-180 records that this
plan was written from the specification and the roadmap without auditing what
P0 had delivered.

`CostRecord` already existed too. This adds `BillingPeriod`, `CostMeasure` and
`CostTotal`. A screen rendering amortized cost under a label saying billed is a
defect nobody can see by reading it, and the four measures are equal often
enough that it survives review.

**Files.**

| Path | Action |
| --- | --- |
| `finops_core/ports/cost.py` | unchanged. Read before assuming, which is the only reason this task shrank |
| `finops_core/domain/cost.py` | extended, `BillingPeriod`, `CostMeasure` and `CostTotal` |
| `finops_core/domain/__init__.py` | the three exported |
| `tests/core/test_cost_domain.py` | created, 15 tests |

**Acceptance criteria.**

- [x] `finops_core` still imports no boto3, no framework and no HTTP client,
      which import-linter already enforces
- [x] A `CostTotal` cannot be constructed without a measure, and two totals of
      the same amount with different measures are not equal
- [x] `BillingPeriod.is_open` is derived from the period's end against a clock
      passed in, never from `datetime.now()` inside the type. A naive datetime
      is refused with a message that says what is wrong
- [x] The end is exclusive, which the fixtures already assumed and nothing had
      written down. August is `2026-08-01` to `2026-09-01`, and reading that
      end as inclusive counts a day of September into August
- [x] Money is `Decimal` and a float is refused at construction. The module
      docstring already said so and a docstring has never refused anything

**Deliberately not in this task.** No adapter, no collector. A port with two
implementations and no caller is the right amount of nothing to have built.

---

### TASK-P1-002: a fake estate with a bill

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-18 |
| Implements | P1 spec sections 4 and 11 |
| Delivers | FEAT-020 |
| Depends on | TASK-P1-001 |
| Estimate | M |

**Goal.** A synthetic estate in FOCUS 1.1 shape, with a configurable failure.

**Part of this exists.** `FakeProvider` already implements `CostExport` against
`fixtures.COST_ROWS`, which is four rows: one per account, one service, one
period, every row tagged, no `resource_id`, and every cost exactly $1.00. That
is enough to prove the port and not enough to exercise a screen. ISS-180. This
task decides whether the richer estate lives in its own module, as
`FakeQuerySurface` does, or stays on `FakeProvider`.

The estate has to contain the states the screens exist to tell apart, or the
screens can look finished while rendering one case. It needs more than one
account, more than one service, a resource level row and a row with no
`resource_id`, tagged rows and untagged rows so the unallocated bucket is not
empty, an open period and a closed one, and a period that can be restated on
demand so TASK-P1-005 has something to restate.

**Files.**

| Path | Action |
| --- | --- |
| `finops_providers/fake/cur.py` | created, `FakeCostExport` and the estate that fills it |
| `finops_providers/fake/provider.py` | delegates to it, so there is one implementation of the port |
| `finops_core/domain/cost.py` | `source_fingerprint`, shared so the fake and the collector cannot disagree |
| `tests/providers/fake/test_cur.py` | created, 16 tests |
| `tests/core/test_cost_domain.py` | extended, 4 more for the fingerprint |

**Acceptance criteria.**

- [x] Every row is a valid `CostRecord` in FOCUS 1.1 shape, with `Decimal`
      money and both timestamps. **The criterion originally said the rows pass
      the same normalization the AWS adapter's output does, and there is no AWS
      adapter yet.** That comparison is the contract test in TASK-P1-003 and is
      not something this task could have done
- [x] The estate contains untagged rows, so the unallocated bucket has
      something in it before anybody writes the screen. It is $1,366.52 of
      $6,197.65 in the closed period, which is 22 percent and is the kind of
      number the screen exists to surface
- [x] A restatement can be asked for: 2,100 rows become 2,099, exactly one of
      the survivors changed
- [x] A failure can be asked for, by typed cause, and is raised rather than
      returned. `NoData` for an empty period is raised too, because it is the
      one cause a caller may draw as a zero
- [x] More than one service and they cost different amounts, so a ranking
      ranks. EC2 $3,279.18 down to Lambda $204.95 in the closed period
- [x] The open period is a part month, 23 days against 31, so the open period
      label has something to label. Its total is lower than the closed month's,
      which is exactly the trap a reader falls into unwarned
- [x] The account Meter cannot assume a role into is on the bill, because the
      bill comes from the payer. Unreadable and unbilled are different facts
- [x] The fingerprints are the real ones, 2,100 distinct, and computing them
      needed `source_fingerprint` to exist. It is in `finops_core` so both
      adapters produce the same digest, and a test runs it in two processes to
      prove it is not `hash()`, watched failing against a `hash()`
      implementation before being trusted

**Deliberately not in this task.** No random data. A fake whose numbers move
between runs cannot be asserted against, and this project has already been
caught by a green test that measured nothing.

**Scope taken on.** `source_fingerprint` was listed under TASK-P1-004. The port
hands over `CostRecord`, which requires a fingerprint, so the adapter has to set
one, and a fake inventing its own would have proved the collector's upsert
against a shape that cannot occur. One function in `finops_core`, two callers,
no disagreement possible.

---

### TASK-P1-003: the Athena adapter, written and unproved

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-18, and unproved by construction |
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
| `finops_providers/aws/cur.py` | created, `AthenaCostExport` |
| `finops_core/config.py` | five settings for the export location and the workgroup |
| `.env.example` | the same five, which a test holds to the settings |
| `tests/providers/aws/test_cur.py` | created, 15 tests against recorded shapes |
| `tests/contract/conftest.py` | a cost export provider for both sides |
| `tests/contract/test_cost_export.py` | created, 6 sentences over both adapters |
| `finops_providers/fake/fixtures.py` | the smoke fixture's fingerprint made real, which the contract caught |

**Acceptance criteria.**

- [x] The contract test passes against the fake and the AWS adapter. **It
      earned its place immediately**: it failed on the fake, whose smoke fixture
      still used `fake:<account>` as a line item's identity where the collector
      would compute a digest. A fake with an identity the collector cannot
      produce proves the upsert against a shape that cannot occur
- [x] `Throttled` is retried with backoff, and a period still throttled after
      the retries raises. Raising is what "incomplete rather than short" means
      here: the port returns an iterable, so the only way to say incomplete is
      to refuse to return at all
- [x] Athena reporting a throttle as a failed execution rather than as a
      throttled call is still read as a throttle. It is the only place that
      cause appears, and reading it as schema drift sends somebody to look at
      the table
- [x] The query prunes on the billing period partition, and a test asserts no
      function wraps the partition key, because a function applied to it stops
      Athena pruning and the query silently scans the whole table at full price
- [x] A period is returned whole or not at all. A failure part way through
      paging raises rather than returning the pages that arrived, because a
      short list is indistinguishable to the collector from a month where those
      charges were retracted and the delete in TASK-P1-005 turns on exactly
      that difference. The memory ceiling this buys is ISS-181
- [x] A missing required column is `SchemaDrift` and never a zero, per
      constraint 5
- [x] **This adapter has never made a call.** Written, unit tested against
      recorded shapes, held to the contract. None of that is having run. The
      column mapping in `COLUMNS` is the part most likely to be wrong, because
      it is the part only a real export can settle, and it is marked as such in
      the file. ISS-122

**Deliberately not in this task.** No credentials work. The hub role already
reaches the payer, and inventing a second path to it now would be a second
thing to unpick when an account arrives.

**Scope taken on.** Five settings, because an adapter that cannot be told where
the export is has to hardcode it, and the hardcoding gate would refuse that and
be right to. There is deliberately no setting for the Athena result location:
the workgroup carries it, and enforcing it there is what stops a query writing
results wherever the caller fancied.

---

### TASK-P1-004: the collector, and what makes a line item itself

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-18 |
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
| `finops_ingest/collectors/cost_focus.py` | created. `source_fingerprint` already existed, done under TASK-P1-002 |
| `finops_ingest/registry.py` | `run_id` added to `CollectorContext`, defaulted |
| `finops_ingest/worker.py` | passes the claim's run id into it |
| `tests/ingest/collectors/test_cost_focus.py` | created, 10 tests |

**Acceptance criteria.**

- [x] Ingesting a period twice leaves exactly the same rows, proved by counting
      them and comparing, not by arguing that an upsert is idempotent
- [x] A row whose cost changed updates in place and does not duplicate. The
      first version of that test was vacuous: the collector writes the latest
      period and the restatement lands in the closed one, so nothing moved and
      the assertion passed against a collector that did nothing. It now hands
      the collector the closed period and names the corrected fingerprint
- [x] The row's `ingest_run_id` moves to the run that last saw it, which is the
      only signal TASK-P1-005 has that AWS retracted a row rather than that the
      read failed half way
- [x] The fingerprint is stable across process restarts, which rules out
      `hash()`. Proved under TASK-P1-002, in two processes, and watched failing
      against a `hash()` implementation
- [x] A missing partition fails the run rather than misfiling the cost. The
      database refuses it, which is constraint 11 working, and this collector
      does not create partitions to get around it
- [x] A typed failure reaches the caller as itself rather than as a successful
      run of zero rows. **The criterion said one account failing does not fail
      the run, and that does not map here**: CUR is written per payer, so there
      are no per account calls to fail independently. The property that does
      map is the typed cause, and it is tested
- [x] An export that exists and has published nothing raises `NoData` rather
      than succeeding with zero rows, because a run that succeeded and wrote
      nothing reads on the freshness screen as an estate that spent nothing

**Deliberately not in this task.** No delete. Retraction is TASK-P1-005 and is
the only destructive operation in the ingest path, so it gets its own commit
and its own review. A test asserts the retracted row is still present, so a
delete cannot arrive here by accident.

**Not done, with a reason.** The collector is not registered anywhere. Nothing
in production assembles a `CollectorRegistry`: the dispatcher and the worker
both take one, `register_retention` fills one, and the only callers are tests.
Adding a registration line nobody reads would be dead code pretending to be
wiring. ISS-182 records the gap, which is pre existing and not P1's.

---

### TASK-P1-005: retraction, which is the dangerous half

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-18 |
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
| `finops_ingest/collectors/cost_focus.py` | the complete period removal |
| `finops_ingest/registry.py` | `items_removed` on `CollectorOutcome`, defaulted |
| `tests/ingest/collectors/test_cost_focus_restatement.py` | created, 9 tests. Beside the other collector suites rather than at the path this plan guessed |
| `tests/ingest/collectors/conftest.py` | created, one partition teardown instead of a copy per module |

**Acceptance criteria.**

- [x] A restated period drops the retracted row and keeps the rest
- [x] A run that failed part way removes nothing, proved by failing the read
      after 5 rows and again at the 500 row batch boundary, where rows have
      certainly reached the database already
- [x] The removal is keyed on `ingest_run_id` and not on a timestamp. Every run
      in the suite shares one frozen clock, so a timestamp predicate would
      remove nothing or remove everything, and the test would notice either way
- [x] It removes nothing it was not asked to. Another billing period and
      another tenant are both asserted untouched, because without the period
      predicate ingesting August removes every earlier month in one statement
- [x] The estate's total follows the invoice down, not only up
- [x] The run reports what it removed, through `items_removed`, because a
      destructive operation nobody can count is one nobody notices going wrong
- [x] The guard was removed and watched. **The first attempt found the claim
      wrong.** Reversing the two lines did not fail the half read tests at all:
      the worker's transaction rolls the removal back with everything else, so
      those tests were exercising the transaction rather than this collector.
      The comment in `__call__` said order was the whole of the safety property
      and it was not. Corrected, and
      `test_the_collector_alone_removes_nothing_on_a_half_read` now looks at the
      rows inside the transaction before the rollback, which is the test that
      goes red when the two lines are swapped

**Deliberately not in this task.** No soft delete and no retraction history. A
retracted charge is not a fact about the estate, it is a correction to a record
of one, and keeping both invites a screen that adds them together.

**Two protections, and it is worth knowing which is which.** The worker runs a
unit in one transaction, so a failed read rolls back any removal along with
everything else, and that is the one doing the work in the deployed shape. The
ordering is the second, and it matters for any caller that does not wrap the
unit in a transaction it will roll back. Both are kept. Only the second has a
test that can see it.

---

### TASK-P1-006: the monthly rollup, derived and never ingested

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-19 |
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
| `finops_ingest/collectors/cost_rollup.py` | created. One body, two predicates, shared |
| `finops_ingest/collectors/cost_focus.py` | calls it for the period it just wrote |
| `finops_ingest/collectors/retention.py` | calls it instead of its own copy of the same SQL |
| `tests/ingest/collectors/test_cost_rollup.py` | created, 6 tests |

**Acceptance criteria.**

- [x] The monthly total equals the sum of the daily rows for that month, proved
      by a test that sums both and compares, and the line item counts agree too
- [x] A retraction moves the monthly figure in the same transaction, so the two
      are never briefly inconsistent
- [x] Rolling up twice changes nothing
- [x] A group whose every line item was withdrawn is removed. The upsert alone
      cannot do this: it only replaces groups it can still see, so a group with
      nothing behind it would keep its last known total forever. Small,
      permanent, and it only ever points one way
- [x] The retention caller does **not** prune, and a test proves it, because
      that pass exists to make monthly rows outlive the daily partitions it is
      about to drop. Pruning there would delete the archive it just created

**Deliberately not in this task.** No further rollups. A weekly or quarterly
table is a third source for the same number, and nothing has asked for one.

**Found on arrival.** `retention_cost` already wrote `cost_focus_monthly`, for
months past the cutoff, with its own copy of this SQL. So the task was not to
write an aggregate but to stop there being two. The arithmetic is now one
function with two callers, differing only in the predicate and in whether they
may prune.

---

### TASK-P1-007: cadence, as data

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-19 |
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
| `finops_ingest/registry.py` | one `ScheduleEntry` for `cost_focus`, six hourly |
| `tests/ingest/collectors/test_cost_focus.py` | two tests, beside the collector's own |
| `tests/ingest/collectors/test_retention.py` | its exhaustive collector set, which is what caught the addition |

**Acceptance criteria.**

- [x] The interval is a row, with a reason and a cost estimate, because a
      cadence nobody can explain is one nobody can safely change and the first
      thing anyone does with an unexplained interval under cost pressure is
      double it
- [x] `install_default_schedule` never overwrites an operator's change, proved
      by slowing the cadence down and reinstalling
- [ ] Freshness on `/cost` is judged against this cadence. The row exists and
      nothing reads it yet, because the screen arrives at TASK-P1-010. Carried
      there rather than ticked here

**Deliberately not in this task.** OPEN-08 is not answered here. Whether a
month is ever declared final is a decision, and this task ships the cadence the
decision would change.

**A gap this task found and did not close.** `ScheduleEntry` carries one
interval per collector and cannot express the specification's two, which are a
fast re read of the open period and a slow one of closed periods. The collector
only ever reads the latest period, so a restatement of a closed month is never
picked up at all. The retraction machinery would handle it correctly the moment
a closed period is read, so the gap is which periods are asked for rather than
what happens to them. ISS-183.

---

### TASK-P1-008: the guard, then the repository

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-19 |
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
| `finops_api/guards.py` | two rules **corrected**, not added. Both tables were already there, scoped by tenant only. ISS-184 |
| `finops_api/db/repositories/cost.py` | created, `CostRepository` and `MonthlyCostRepository` |
| `tests/api/test_cost_repository.py` | created, 16 tests |

**Acceptance criteria.**

- [x] A narrow scope reads fewer rows than a global one, proved by a test that
      does both. **The rule was wrong before this task, not missing.** Both
      tables were in `SCOPED_TABLES` already, with `None`, so the account was
      never consulted and the first route would have served the whole
      organization's bill to a two account viewer. ISS-184, and three tests were
      watched failing against the old rule
- [x] An empty scope returns nothing and never everything
- [x] Every read writes an `audit_event`, through the base class, in the same
      transaction as the read
- [x] Every grouping sums back to the period total, for all three dimensions.
      A grouping that does not is dropping rows, and on screen that reads as an
      estate smaller than it is
- [x] The period is always named by the caller or asked for by
      `latest_period`. Nothing defaults to this month, which would answer a
      different question in the first minute of a new month than in the last
      minute of the old one
- [x] A tenant with no cost gets `None` rather than a zero, which is a
      different fact from a period that totalled nothing
- [x] The monthly table agrees with the daily one, asserted by summing both

**Deliberately not in this task.** No routes. The repository is provable on its
own and the route is where the scope dependency is added.

**The grouping column is looked up, never interpolated.** A column name that
arrives from a request and is dropped into SQL is an injection. `GROUPABLE` is
three entries long, so refusing everything off it costs nothing.

---

### TASK-P1-009: four routes

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-19 |
| Implements | P1 spec section 8 |
| Delivers | FEAT-021, FEAT-022 |
| Depends on | TASK-P1-008 |
| Estimate | M |

**Goal.** `GET /cost/summary`, `/cost/by-service`, `/cost/by-account` and
`/cost/trend`, all returning the meta envelope.

**Files.**

| Path | Action |
| --- | --- |
| `finops_api/routes/cost.py` | created, four routes |
| `finops_api/main.py` | `p1_routers`, beside `p0_routers` and `p2_routers` |
| `finops_api/schemas.py` | four response models |
| `finops_providers/fake/cur.py` | the estate's periods derived from a clock rather than listed |
| `tests/api/test_cost_routes.py` | created, 15 tests, every one through the client |

**Acceptance criteria.**

- [x] **Every route has been called**, not imported, and the reachability test
      is parameterised over all five paths so a new one cannot be added without
      an answer
- [x] The envelope carries `as_of` and `collected_at` on every figure
- [x] An open period is flagged in the payload, not inferred by the frontend
      from a date. **The first version of that test was asserting the calendar
      rather than the route**: the fake estate's periods were listed constants
      pinned to 2026-08, so its open month had stopped being open. The periods
      are derived from a clock now, which is the fix the demo estate needed
      anyway
- [x] Scope is enforced twice. A narrow scope is served strictly less than a
      global one, through the client, and `by-account` shows it only its own
- [x] A tenant with no cost gets a 404 and never a zero. Zero spend is a claim,
      an estate nobody has collected is an absence, and constraint 5 is about
      exactly that difference
- [x] No previous period gives a null change rather than no movement, because a
      change computed against a month nobody collected is a number invented out
      of an absence
- [x] Every grouping and the daily series sum back to the summary, asserted
      through the client rather than in the repository only
- [ ] A typed collection failure reaches the trust strip by the same path an
      unreachable workspace does. **Not done**: no cost collection failure is
      recorded against a scope yet, because the collector runs organization
      wide and `sync_error` is keyed per scope. Carried as a known gap rather
      than ticked

**Deliberately not in this task.** No allocation route. Allocation is a
grouping of these rows by a tag key, and a fifth route would be a second
implementation of one query.

---

### TASK-P1-010: the spend and trend screen

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-19 |
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
| `finops-web/src/api/queries.ts` | five hooks |
| `finops-web/src/api/types.ts` | four response types |
| `finops-web/src/api/fixtures/cost.ts` | created |
| `finops-web/src/App.tsx` | the two routes |
| `finops-web/src/shell/sections.ts` | both placeholders replaced |
| `finops-web/src/screens/__tests__/CostScreen.test.tsx` | created, 8 tests |

**Acceptance criteria.**

- [x] The open period is labelled beside the figure, not in a footnote
- [x] Every figure goes through `Figure`, so provenance and freshness are on the
      screen rather than in the payload
- [x] No earlier period renders as a sentence, never as a change of nought
- [x] ADR-0021 holds and `surface.test.ts` still passes
- [x] No accessibility violations
- [x] **Opened at 1460px and read, which found two defects no test had.** The
      coverage banner said "showing all 450 accounts" on an estate with five,
      because the line item count was passed where the banner names accounts.
      And the trend rendered as eighteen rows each repeating the same freshness
      sentence, which is not a trend, it is one sentence eighteen times around
      numbers nobody can compare. Both fixed: the banner counts accounts, and
      the trend is a sparkline with its two ends written out

**Deliberately not in this task.** No per resource drill down. The rows are
stored and the screen for them is a separate decision.

---

### TASK-P1-011: the allocation screen and the bucket nobody wants

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-19 |
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
| `finops-web/src/screens/__tests__/CostAllocationScreen.test.tsx` | created, 6 tests |

**Acceptance criteria.**

- [x] The unallocated row is visible and never folded into a total. It reads
      "nobody tagged this" rather than being blank, because an empty cell looks
      like a rendering fault and sends somebody looking for a value that was
      never there
- [x] The share is stated as a percentage, so a reader does not have to divide
      it themselves to know whether it matters. On the seeded estate it is 22.0
- [x] The tag key is chosen, with no default at the API. Guessing one would
      group an estate by something nobody asked for and label it their
      allocation
- [x] The same freshness, provenance and failure rules as TASK-P1-010

**Deliberately not in this task.** No Cost Categories. Tags first, and a second
allocation source before the first is proved makes a disagreement between them
impossible to attribute.

---

### TASK-P1-012: the demo estate gets a bill

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-19 |
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
| `scripts/ops/seed_demo.py` | partitions, the cost collector per period, and three tables in `DEMO_TABLES` |
| `finops-web/e2e/cost.spec.ts` | created |
| `finops-web/e2e/journey.spec.ts` | its unbuilt screen journey repointed at anomalies |
| `tests/scripts/test_seed_demo.py` | the three cost tables removed from `never_seeded` |
| `.env` | the five CUR settings, locally |

**Acceptance criteria.**

- [x] `make seed` fills `/cost` and `/cost/allocation`, proved by opening both
      through nginx: 2,234 rows, $3,489.84 in an open period against $6,197.65
      the month before
- [x] `make unseed` removes every cost row, and the derived teardown test now
      covers the three cost tables rather than declaring them never seeded
- [x] The bill differs by day, so the trend is a shape rather than one number
      drawn eighteen times
- [x] The journey opens `/cost`, reads a figure and follows it to
      `/cost/allocation`
- [x] **The seed creates the partitions for the months it writes.**
      `partition_maintenance` creates the current month and the ones ahead,
      which is right for a running system and useless for a seed reaching two
      months back. The collector refused the rows rather than misfiling them,
      which is constraint 11 doing its job, and the seed now says which months
      it is about to write
- [x] The seed ingests every period the estate holds, one run each. The
      collector reads only the latest period, ISS-183, so a single run leaves
      the summary with nothing to compare against, which is the first figure a
      person looks at

**Deliberately not in this task.** No fake anomalies. There is no anomaly
screen to show them on.

**A consequence worth knowing about.** The five CUR settings TASK-P1-003 added
are required, so a deployment that does not set them refuses to start. That is
the right failure, and the message names all five, but it is a breaking config
change: the local stack crash looped until `.env` carried them. `.env.example`
has them and is what a new environment copies.

---

### TASK-P1-013: the infrastructure that will not be applied

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-19, and unapplied by construction |
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
| `infra/terraform/hub/variables.tf` | two variables, both with a validation and a reason |

**Acceptance criteria.**

- [x] `terraform validate` and `terraform fmt -check` pass, which is syntax,
      provider schema and references
- [x] Every resource carries `finops:module`, per constraint 7, through the
      provider's `default_tags` rather than by being repeated on each resource
- [x] The Athena workgroup has a bytes scanned cutoff, because a query that
      forgets to prune the partition scans the whole table at full price and
      reads as nothing worse than a slow query until the bill arrives
- [x] The export bucket is separate from the data bucket, because that one has
      a lifecycle rule that expires derived artefacts and a billing export is
      the record of what was charged
- [x] The bucket policy is conditioned on this account, so a leaked policy
      could not let another account write into it
- [x] `make security-scan` passes with zero unresolved. The one finding it
      raised, no access logging on the new bucket, was **fixed rather than
      allowlisted**: a bucket holding the record of what an organization was
      charged should record who read it
- [x] **Nothing has been planned and nothing has been applied.** ISS-122. The
      task is done when the stack validates, and this document says that is what
      done means here

**Deliberately not in this task.** No member account IAM. CUR is read from the
payer, which the hub role already reaches.

---

# Second cut

Section 3 of the specification deferred these three with a reason each. The
reasons have not gone away, so each task below says how it is dealt with rather
than pretending it was never raised.

---

### TASK-P1-014: a day that does not look like the days before it

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P1 spec section 16, FEAT-023 |
| Delivers | FEAT-023 |
| Depends on | TASK-P1-006 |
| Estimate | L |

**Goal.** Detect a day whose cost for one account and service is out of keeping
with the days before it, and write it to `cost_anomaly`.

**The objection, and what answers it.** Section 3 said an anomaly is a deviation
from a baseline and there is no baseline until the surface has collected for
weeks, so building the detector first means tuning it against fabricated
history. That is still true. What changes is that the detector is now written to
**refuse** rather than to guess: fewer than 14 days of history for a pair
produces no verdict at all, not a quiet zero and not a cautious one. The
threshold is a row, so tuning it against a real estate is a configuration change
rather than a release.

**Files.**

| Path | Action |
| --- | --- |
| `migrations/versions/0008_cost_anomaly.py` | created |
| `finops_query/anomaly.py` | created, the arithmetic, no IO |
| `finops_ingest/collectors/cost_anomaly.py` | created |
| `tests/query/test_anomaly.py` | created |
| `tests/ingest/collectors/test_cost_anomaly.py` | created |

**Acceptance criteria.**

- [ ] Fewer than 14 days of history for a pair produces no verdict, and a test
      asserts the absence rather than a zero
- [ ] The baseline is a median and a median absolute deviation, not a mean and a
      standard deviation. One spike in the baseline window drags a mean up far
      enough to hide the next spike, which is the failure mode that matters
- [ ] A deviation under a dollar floor is not an anomaly however large the
      ratio. A service costing two cents that triples is not news, and ADR-0016
      says severity comes from the money
- [ ] Severity comes from the dollar delta, through the same `severity_for` the
      query findings use, so two screens do not mean different things by high
- [ ] Re running the detector for a day it has already judged changes nothing
- [ ] The arithmetic is in `finops_query` with no database and no clock, so it
      can be tested on lists

**Deliberately not in this task.** No ingest of AWS Cost Anomaly Detection
findings. That is a second source with its own port and no way to be proved,
and a screen showing two detectors that disagree is worse than one that does
not. It is named in the feature document as the part that waits on ISS-122.

---

### TASK-P1-015: the anomalies screen

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P1 spec section 16 |
| Delivers | FEAT-023 |
| Depends on | TASK-P1-014 |
| Estimate | M |

**Goal.** `/cost/anomalies`. What changed, by how much, on which day, and for
whom.

**Files.**

| Path | Action |
| --- | --- |
| `finops_api/guards.py` | `cost_anomaly` scoped `ByAccount` |
| `finops_api/db/repositories/cost.py` | the anomaly read |
| `finops_api/routes/cost.py` | `GET /cost/anomalies` |
| `finops-web/src/screens/CostAnomaliesScreen.tsx` | created |
| `tests/api/test_cost_routes.py` | extended |
| `finops-web/src/screens/__tests__/CostAnomaliesScreen.test.tsx` | created |

**Acceptance criteria.**

- [ ] The guard entry goes in before the route, and a test reads out of scope
      and is refused
- [ ] Every row says what it was, what it was expected to be, and the difference
      in money. A percentage alone is not actionable
- [ ] An estate with no anomalies is a sentence, not an empty table, and it is
      distinguishable from an estate with too little history to judge
- [ ] The route is called, not imported

---

### TASK-P1-016: what was committed, and how much was used

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P1 spec section 16, FEAT-024 |
| Delivers | FEAT-024 |
| Depends on | TASK-P1-001 |
| Estimate | L |

**Goal.** A port for commitment utilization and coverage, a fake, an unproved
AWS adapter, a collector and a table.

**The objection, and what answers it.** Section 3 said this comes from a
different API on a different cadence, and it does. That is why it is its own
port and its own collector rather than a widening of `CostExport`: a Savings
Plan is not a line item and modelling it as one would put a second meaning on
`cost_focus_daily`.

**Files.**

| Path | Action |
| --- | --- |
| `migrations/versions/0009_commitment_coverage.py` | created |
| `finops_core/ports/commitment.py` | created |
| `finops_core/domain/cost.py` | `CommitmentUse` |
| `finops_providers/fake/commitment.py` | created |
| `finops_providers/aws/commitment.py` | created, unproved |
| `finops_ingest/collectors/commitment.py` | created |
| `tests/contract/test_commitment.py` | created |

**Acceptance criteria.**

- [ ] Utilization and coverage are separate numbers and neither is derived from
      the other. A commitment can be fully used and cover a tenth of the estate,
      and the two questions have different answers and different actions
- [ ] An expired commitment is reported as expired, not dropped, because the
      money was spent and the coverage gap it leaves is the finding
- [ ] The AWS adapter has never made a call, and the document says so
- [ ] Contract tested against both adapters

---

### TASK-P1-017: the commitments screen

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P1 spec section 16 |
| Delivers | FEAT-024 |
| Depends on | TASK-P1-016 |
| Estimate | M |

**Goal.** `/cost/commitments`. What is committed, what it covers, what it wasted.

**Acceptance criteria.**

- [ ] Utilization and coverage are both shown and are labelled distinctly enough
      that nobody reads one as the other
- [ ] Unused commitment is money already spent, and it is shown in money
- [ ] The guard entry precedes the route, and the route is called

---

### TASK-P1-018: the file finance opens

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P1 spec section 16, FEAT-045 |
| Delivers | FEAT-045 |
| Depends on | TASK-P1-009 |
| Estimate | M |

**Goal.** `GET /cost/export`, a CSV of one period at the grain finance asks for:
account, service, tag value, amortized, billed, line items.

**The objection, and what answers it.** Section 3 said an export of a surface
still changing shape is one nobody can rely on. The surface stopped changing
when tasks 008 to 011 landed, and the export is generated from the same
repository the screens read, so it cannot drift from what they show.

**Files.**

| Path | Action |
| --- | --- |
| `finops_api/routes/cost.py` | `GET /cost/export` |
| `finops-web/src/screens/CostExportScreen.tsx` | created |
| `tests/api/test_cost_export.py` | created |

**Acceptance criteria.**

- [ ] The file's totals equal the screen's totals, asserted by summing the CSV
      and comparing against `/cost/summary`. A file that disagrees with the
      screen is worse than no file
- [ ] The unallocated bucket is a row in the file, named, never dropped
- [ ] Every figure says which measure it is, in the header, because a column of
      numbers in a spreadsheet has nothing else to say it
- [ ] Scoped like every other read, and a narrow scope exports less
- [ ] Excel is **not** in this task, and the feature document says why

---

### TASK-P1-019: the demo estate

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P1 spec section 16 |
| Delivers | FEAT-023, FEAT-024 |
| Depends on | TASK-P1-015, TASK-P1-017 |
| Estimate | M |

**Goal.** The seeded estate contains an anomaly worth looking at and a
commitment worth acting on, so the screens have something to show.

**Acceptance criteria.**

- [ ] The fake estate contains one genuine spike, produced by the estate rather
      than inserted into the table, so the detector finds it rather than being
      told about it
- [ ] It contains a commitment that is fully used and one that is not, because
      those are the two conversations
- [ ] `make unseed` removes every new table, held by the derived teardown test

---

### TASK-P1-020: the design pass

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | ADR-0021, `docs/12-UI-DESIGN.md` |
| Delivers | Nothing new. It makes what exists legible |
| Depends on | TASK-P1-019 |
| Estimate | L |

**Goal.** Every screen readable at a glance by somebody who did not build it.

**What this is not.** It is not a restyle. The tokens, the warm severity ramp
and IBM Plex are already decided and already used by Home. This is the pass that
applies them consistently, gives each screen a shape, and removes the places
where a functional screen reads as an unfinished one.

**Acceptance criteria.**

- [ ] Every screen has been opened at 1440px and read, and the list of what that
      found is written down. That pass found two defects on `/cost` alone that
      no test had
- [ ] ADR-0021 holds: `layout.css` targets no class a component had to add, and
      `surface.test.ts` passes
- [ ] No accessibility violations on any screen
- [ ] Dark mode is checked, not assumed
- [ ] Nothing is made to look more certain than it is. A modelled figure still
      reads as modelled after the pass, and a failure still reads as a failure

---

### TASK-P1-021: the demo walk

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P1 spec section 16 |
| Delivers | Nothing new |
| Depends on | TASK-P1-020 |
| Estimate | S |

**Goal.** One journey that walks the whole product in the order a person would
demonstrate it, and a written script for the person driving.

**Acceptance criteria.**

- [ ] The journey visits Home, the cost surface, governance and inventory, and
      asserts a figure on each, so a broken screen fails the build rather than
      the demo
- [ ] `docs/runbooks/demo.md` says what to run, in what order, and which three
      numbers to point at
- [ ] It says plainly which parts are fake, because a demo that implies a live
      AWS connection is a demo that creates a promise somebody has to keep
