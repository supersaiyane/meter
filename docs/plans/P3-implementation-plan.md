# P3 Utilization and Rightsizing: implementation plan

Date: 2026-09-20
Status: Provisional, pending approval of `docs/specs/2026-09-20-p3-utilization-and-rightsizing-design.md`
Spec: `docs/specs/2026-09-20-p3-utilization-and-rightsizing-design.md`
Depends on: P0 delivered, P1 delivered
Tasks: 20

P1 says what the estate costs. This says what it should cost instead, names who
will change it, and then checks whether the bill moved. The last of those is the
sub project; the rest is upstream of it.

## How to work this plan

Same contract as P0, P1 and P2. Read `docs/03-CHANGE-CONTROL.md`, section "The
anti hallucination contract", before starting.

One task, one commit. Read the **Deliberately not in this task** list before
writing code, not after. If reality does not match the spec, stop, raise an
`ISS-nnn`, fix the spec, add a `CHG-nnnn`, then continue.

**Five rules specific to P3.**

1. **There is still no AWS account.** ISS-122. Every task is built and proved
   against a fake estate. The tasks writing AWS adapters say in their own
   acceptance criteria that they have never run, rather than letting a green test
   imply an integration.

2. **Estimated and realized savings are different kinds of number.** Estimated is
   modelled, realized is measured, and P1 already built the vocabulary for that
   distinction. They live in different tables, render in different columns, and
   TASK-P3-014 writes a test that tries to add them and requires a failure.

3. **Confidence is not severity.** Severity comes from the money, ADR-0016.
   Confidence comes from how much data the estimate rests on. A task finding
   itself combining them has found a disagreement with the spec.

4. **The guard entry goes in before the route.** The rule P1 inherited from
   TASK-P2-021 and ISS-184. TASK-P3-010 does the guard, and the routes do not
   start until a test has read out of scope and been refused.

5. **Nothing writes to a member account.** Constraint 6. The existing read only
   contract test covers it, and every task here stays under it.

## Wave overview

| Wave | Tasks | Delivers | Can start when |
| --- | --- | --- | --- |
| A. Domain and ports | 001 to 002 | The recommendation entity, the ports, and the arithmetic with no database in it | P1 delivered |
| B. AWS native ingest | 003 to 005 | Cost Optimization Hub, Compute Optimizer and Trusted Advisor, in one table | A |
| C. Bespoke waste | 006 to 008 | What AWS is blind to, from metrics, batched and floored at 14 days | A |
| D. CloudWatch module | 009 | The cheap wins in the service that bills for watching | C |
| E. Lifecycle | 010 to 012 | The guard, the routes, the events and a ticket port | B, C |
| F. Realized savings | 013 to 014 | The north star, and the proof it cannot be inflated | E |
| G. Score | 015 to 016 | A number that decomposes, or no number | F |
| H. Screens | 017 to 019 | Three screens and a journey | E, F, G |
| I. Blast radius | 020 | Scoring that refuses rather than guesses. **Needs P4** | H, P4 delivered |

Wave I is deliberately last and outside this sub project's own dependency chain.
FEAT-044 reads P4's edge tables, so it cannot be built before them. Ordering it
here rather than reordering the sub projects keeps the money features first, which
is the decision recorded on 2026-09-20.

---

### TASK-P3-001: the recommendation entity, and the two numbers it refuses to merge

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-21 |
| Implements | P3 spec sections 4 and 5, FEAT-028 |
| Delivers | Part of FEAT-028 |
| Depends on | P1 delivered |
| Estimate | M |

**Goal.** `Recommendation`, `Confidence`, `Lifecycle` and `SavingsEstimate` in
`finops_core/domain/waste.py`, with money as `Decimal` and both timestamps.

**The objection, and what answers it.** A single score combining money and
certainty is the obvious simplification, and it is why most tools cannot tell you
whether to act on a large uncertain recommendation this week. The entity refuses
the merge at construction: `severity` is derived from the money and `confidence`
from `observation_days`, by two functions that do not see each other's input.

**Files.**

| Path | Action |
| --- | --- |
| `finops_core/domain/waste.py` | created |
| `tests/core/test_waste_domain.py` | created |

**Acceptance criteria.**

- [ ] A recommendation with fewer than 14 observation days cannot be constructed
- [ ] `severity` is computed from the money through the same `severity_for` the
      query findings and the anomalies already use, so three screens mean the same
      thing by the word high
- [ ] `confidence` is computed from `observation_days` alone, and a test proves
      that changing the money does not change it
- [ ] Money refuses `float`, as `CostTotal` already does
- [ ] Inherits `Fact`, so it is covered by `test_as_of_is_required`

**Deliberately not in this task.** No table, no port, no provider. The entity
first, so the ports have something to be about.

---

### TASK-P3-002: the arithmetic, with no database and no clock in it

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-21 |
| Implements | P3 spec section 4, FEAT-026 |
| Delivers | Part of FEAT-026 |
| Depends on | TASK-P3-001 |
| Estimate | M |

**Goal.** `finops_query/waste.py`. p95 and p99 over a series, the 14 day refusal,
and one saving estimate function per waste class.

**The objection, and what answers it.** This could live in the collectors, next to
the data it reads. `finops_query/anomaly.py` did not, and that is what let its
three load bearing decisions be tested against lists rather than against a
fixture. The same applies here and more so, because a rightsizing estimate is
arithmetic somebody will eventually dispute.

**Files.**

| Path | Action |
| --- | --- |
| `finops_query/waste.py` | created |
| `tests/query/test_waste.py` | created |

**Acceptance criteria.**

- [ ] p95 and p99, never max. A single spike must not size an instance
- [ ] Fewer than 14 days returns no estimate at all, not a cautious one. The same
      `MINIMUM_HISTORY` the anomaly detector uses, imported rather than repeated,
      so two features cannot drift on what enough history means
- [ ] Burstable credit balance is an input, and an instance at 20 percent with a
      healthy credit balance produces no recommendation. A test asserts it
- [ ] Every estimate returns its working as a sentence, as `Verdict.reason` does
- [ ] No import of `sqlalchemy`, `boto3` or `datetime.now`

**Deliberately not in this task.** No collector. The arithmetic is proved against
lists first.

---

### TASK-P3-003: the recommendation port, and one table for every source

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-21 |
| Implements | P3 spec section 5.1, FEAT-025 |
| Delivers | Part of FEAT-025 |
| Depends on | TASK-P3-001 |
| Estimate | M |

**Goal.** `finops_core/ports/recommendations.py`, and the migration creating
`recommendation` and `recommendation_event`.

**Files.**

| Path | Action |
| --- | --- |
| `finops_core/ports/recommendations.py` | created |
| `migrations/versions/0010_recommendations.py` | created |

**Acceptance criteria.**

- [ ] One `recommendation` table with a `source` column, not one table per
      provider service. A lifecycle that works for Compute Optimizer and not for
      an unattached volume is two lifecycles
- [ ] Unique on `(tenant_id, source, source_reference)`, so a re read updates
- [ ] Check constraints on `observation_days >= 14`, non negative money, and every
      enumeration, per constraint 11
- [ ] `recommendation_event` is append only, with no update path in the schema
- [ ] Backward compatible, constraint 12

---

### TASK-P3-004: the AWS adapters that have never run

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-21 |
| Implements | P3 spec section 4, FEAT-025 |
| Delivers | Part of FEAT-025 |
| Depends on | TASK-P3-003 |
| Estimate | L |

**Goal.** `finops_providers/aws/recommendations.py`, reading Cost Optimization
Hub, Compute Optimizer and Trusted Advisor.

**Files.**

| Path | Action |
| --- | --- |
| `finops_providers/aws/recommendations.py` | created, unproved |
| `tests/providers/aws/test_recommendations.py` | created |

**Acceptance criteria.**

- [ ] Every response field that becomes money is parsed or refused as
      `SchemaDrift`, never defaulted to zero
- [ ] `NotOptedIn` is raised as itself when Compute Optimizer is not enabled, and
      the docstring says this is an expected state rather than a fault
- [ ] Trusted Advisor limit checks are attempted, and their absence under a
      support tier without them is `NotOptedIn`, not an empty list. OPEN-03
- [ ] **The file says in its first line that it has never made a call**, as
      `aws/cur.py` and `aws/commitment.py` do, and names the field most likely to
      be wrong
- [ ] Held to the contract suite alongside the fake

---

### TASK-P3-005: the AWS native collector

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-21 |
| Implements | P3 spec section 7, FEAT-025 |
| Delivers | FEAT-025 |
| Depends on | TASK-P3-004 |
| Estimate | M |

**Goal.** `finops_ingest/collectors/recommendations.py`, upserting on the
provider's own identifier, and a `collector_schedule` row with its cost.

**Acceptance criteria.**

- [ ] A second run over an unchanged estate leaves the row count unchanged
- [ ] A recommendation AWS has withdrawn is not deleted. It moves to `DISMISSED`
      with a reason naming the withdrawal, because a row that vanishes takes its
      lifecycle history with it
- [ ] A recommendation a human has already `ACCEPTED` is not reopened by a re
      read. The provider owns the finding, the lifecycle is ours
- [ ] The schedule row carries its reason and its cost, ADR-0012

---

### TASK-P3-006: a fake estate with waste that is not waste

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-21 |
| Implements | P3 spec section 11, FEAT-026 |
| Delivers | Part of FEAT-026 |
| Depends on | TASK-P3-002 |
| Estimate | M |

**Goal.** `finops_providers/fake/recommendations.py`, and metric series in the
fake estate that the bespoke collectors read.

**The objection, and what answers it.** A fake where every low utilization
instance is wasteful proves nothing about a detector: it passes whether or not the
detector is right. This fake contains three things that look like waste and are
not, and a test above it must still find only the real waste.

**Acceptance criteria.**

- [ ] A burstable instance at 20 percent with a healthy credit balance, which is
      correctly sized
- [ ] A development instance idle at night and busy by day, which is not waste
- [ ] An instance with 9 days of history, which is under the floor and produces
      nothing
- [ ] At least one genuine instance of every waste class in spec section 5.2
- [ ] Sized from the estate rather than written down, as the commitment fake is,
      so the numbers cannot drift from the bill

---

### TASK-P3-007: reading metrics without spending a fortune on it

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-21 |
| Implements | P3 spec sections 7 and 12, FEAT-026 |
| Delivers | Part of FEAT-026 |
| Depends on | TASK-P3-006 |
| Estimate | L |

**Goal.** `finops_providers/aws/waste.py`. `GetMetricData`, batched at 500 metrics
per call at a one hour period.

**The objection, and what answers it.** The batching rule reads like premature
optimisation. It is not: `GetMetricData` is charged per metric requested, and a
naive one call per instance implementation on a three hundred account estate is a
line item that would appear on our own platform cost screen. The rule is in the
specification so it is not left to somebody's judgement at three in the afternoon.

**Acceptance criteria.**

- [ ] Batched at 500, asserted by a test counting calls for 1,200 metrics
- [ ] One hour period, not one minute
- [ ] A window that returned no data points raises or reports unobserved, and
      **never** yields a zero utilization reading. A test asserts that an empty
      response does not produce an idle recommendation
- [ ] Never run against AWS, and says so

---

### TASK-P3-008: the bespoke waste collector

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-21 |
| Implements | P3 spec section 7, FEAT-026 |
| Delivers | FEAT-026 |
| Depends on | TASK-P3-007 |
| Estimate | L |

**Goal.** `finops_ingest/collectors/waste_compute.py`, writing `METER` sourced
recommendations for the compute and storage classes.

**Acceptance criteria.**

- [ ] Recommends at Auto Scaling group level, not per instance, where the instance
      belongs to one. FEAT-026's binding rule
- [ ] Every row carries `observation_days` and a rationale sentence
- [ ] The three non waste cases in TASK-P3-006 produce no rows, asserted
- [ ] Partial failure is first class: one account failing does not fail the run

---

### TASK-P3-009: the module that bills for watching

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-21 |
| Implements | P3 spec section 5.2, FEAT-027 |
| Delivers | FEAT-027 |
| Depends on | TASK-P3-008 |
| Estimate | M |

**Goal.** `finops_ingest/collectors/waste_cloudwatch.py`. Log groups with no
retention, high ingest groups unqueried in 90 days, duplicate delivery, unqueried
custom metrics, alarms stuck in insufficient data.

**The objection, and what answers it.** P2 already reads CloudWatch query
evidence, so this looks like duplication. It is not: P2 asks what the queries
cost, this asks what the storage and the metrics cost, and the two read different
APIs for different questions. The shared part is the evidence of what was queried,
and this task reads P2's existing tables rather than re reading the source.

**Acceptance criteria.**

- [ ] A log group with no retention policy is a finding, with the money it would
      save at the default retention
- [ ] Unqueried in 90 days is read from P2's evidence tables, not re collected
- [ ] An alarm in insufficient data for 30 days is a finding. One in insufficient
      data for an hour is not
- [ ] Remediation names the lever: a retention policy, Infrequent Access, or
      export to S3

---

### TASK-P3-010: the guard, before any route

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-21 |
| Implements | P3 spec section 8, constraint 3 |
| Delivers | Part of FEAT-028 |
| Depends on | TASK-P3-003 |
| Estimate | S |

**Goal.** `recommendation`, `recommendation_event` and `realized_saving` in
`SCOPED_TABLES`, with the rule argued in a comment.

**The objection, and what answers it.** None. This task exists because
TASK-P2-021 wrote six routes over six unguarded tables, and ISS-184 found two more
with the rule `None` on the widest tables in the schema. The guard goes in first,
every time, and a test reads out of scope and is refused before a route exists.

**Acceptance criteria.**

- [ ] `recommendation` is `ByAccount("sub_account_id")`, because a recommendation
      names the account its resource lives in
- [ ] `recommendation_event` is `Through("recommendation", ...)`, because an event
      has no account of its own and inherits the one it hangs off
- [ ] `realized_saving` is `Through("recommendation", ...)` for the same reason
- [ ] A test reads each table out of scope and is refused, and is watched failing
      with the rule removed

---

### TASK-P3-011: the lifecycle, and the ticket port with no adapter

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-21 |
| Implements | P3 spec sections 5.3 and 13, FEAT-028 |
| Delivers | Part of FEAT-028 |
| Depends on | TASK-P3-010 |
| Estimate | L |

**Goal.** The transitions, the events, and `finops_core/ports/tickets.py` with a
fake.

**The objection, and what answers it.** OPEN-05 has been open since 2026-08-23,
and building the lifecycle around an unchosen ticketing system looks like
guessing. It is the opposite: the port is what lets the whole lifecycle be built
and tested now, with the Jira or ServiceNow adapter as one later task. Decided on
2026-09-20.

**Acceptance criteria.**

- [ ] Every transition writes a `recommendation_event` naming who and when
- [ ] An illegal transition is refused. `VERIFIED` does not go back to `OPEN`
- [ ] Dismissal requires a reason, enforced by the route rather than by the screen
- [ ] A recommendation with no owner is reported as such on the screen, because
      ISS-021's lesson is that an unowned finding is never fixed
- [ ] `TicketSink` has a fake and no adapter, and the file says why

---

### TASK-P3-012: the routes

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-21 |
| Implements | P3 spec section 8, FEAT-028 |
| Delivers | FEAT-028 |
| Depends on | TASK-P3-011 |
| Estimate | M |

**Goal.** The six routes in spec section 8, every one called through the client in
its tests.

**Acceptance criteria.**

- [ ] Every route returns the envelope, per the contract in `finops_api/main.py`
- [ ] A narrow scope is served fewer recommendations, asserted
- [ ] The coverage banner counts accounts, and a test asserts the unit and the
      figure against another route. Three times a row count has reached that slot;
      see `tasks/lessons.md`
- [ ] `POST` transitions carry no body

---

### TASK-P3-013: what actually appeared in the bill

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P3 spec sections 5.4 and 5.5, FEAT-029 |
| Delivers | Part of FEAT-029 |
| Depends on | TASK-P3-012 |
| Estimate | L |

**Goal.** `finops_ingest/collectors/realized_savings.py` and the `realized_saving`
table, reading `cost_focus_daily` 60 days after `done_at`.

**The objection, and what answers it.** Comparing cost before and after is not a
saving, because the workload may simply have shrunk. That objection is correct and
is why the verdict has three values rather than two. See spec section 5.5.

**Acceptance criteria.**

- [ ] Both cost and usage quantity are compared over matched windows
- [ ] Where usage fell by more than cost, the verdict is `INCONCLUSIVE`
- [ ] A saving that did not persist is `REGRESSED`, and the fake estate produces
      one so the path is exercised in the direction that matters
- [ ] `why` carries the working, including both windows and both quantities
- [ ] Never estimates. This collector reads measured rows only

---

### TASK-P3-014: the two numbers that must not be added

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P3 spec section 2, FEAT-029 |
| Delivers | FEAT-029 |
| Depends on | TASK-P3-013 |
| Estimate | S |

**Goal.** A test that tries to sum estimated and realized savings and is stopped,
and the route and screen shapes that make the sum unavailable.

**The objection, and what answers it.** A test asserting that something cannot be
done reads as ceremony. It is the cheapest possible guard against the one failure
mode ISS-029 names: every tool inflates identified savings, and the inflation
always happens by quietly adding a modelled number to a measured one.

**Acceptance criteria.**

- [ ] The two figures are returned by different routes and typed differently
- [ ] No response object holds both in a way a caller could sum
- [ ] A test attempts the sum and fails to type check or fails to run, and the
      test name says which

---

### TASK-P3-015: a score that decomposes, or no score

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P3 spec section 9, FEAT-043 |
| Delivers | Part of FEAT-043 |
| Depends on | TASK-P3-014 |
| Estimate | L |

**Goal.** `finops_query/score.py`. A 0 to 100 score per account and per team, with
its components.

**The objection, and what answers it.** FEAT-043 already answered it, and the
answer is its ship condition: a score that cannot be taken apart is not a score,
it is an opinion with a number on it. The decomposition is not a reporting feature
added afterwards, it is the return type.

**Acceptance criteria.**

- [ ] `score()` returns components, never a bare number
- [ ] Every component names the findings that produced it
- [ ] A test changes one finding and asserts which component moved and by how much
- [ ] A scope with no findings has **no score** rather than a score of 100,
      because a perfect score for an estate nobody has looked at is the worst
      possible output of this feature

---

### TASK-P3-016: the score collector and its history

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P3 spec section 7, FEAT-043 |
| Delivers | FEAT-043 |
| Depends on | TASK-P3-015 |
| Estimate | M |

**Goal.** Six hourly, written with its components, so a change between two runs is
explainable.

**Acceptance criteria.**

- [ ] Each run stores its components, not only its total
- [ ] A difference between two runs resolves to a list of findings that opened or
      closed, asserted by a test
- [ ] Backward compatible migration, constraint 12

---

### TASK-P3-017: the recommendations screen

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P3 spec section 9 |
| Delivers | Part of FEAT-028 |
| Depends on | TASK-P3-012 |
| Estimate | M |

**Goal.** `/waste`, ranked by money.

**Acceptance criteria.**

- [ ] Money and confidence are not adjacent columns, for the reason the
      commitments screen keeps its two percentages apart
- [ ] The estimate is labelled modelled, using the existing `Figure` provenance
- [ ] A recommendation with no owner says so rather than rendering blank
- [ ] `arrives` is cleared in `sections.ts`, and the derived unbuilt screen tests
      still pass because other screens remain unbuilt
- [ ] No accessibility violations

---

### TASK-P3-018: the screen that is allowed to disappoint

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P3 spec section 9, FEAT-029 |
| Delivers | Part of FEAT-029 |
| Depends on | TASK-P3-014, TASK-P3-017 |
| Estimate | M |

**Goal.** `/waste/savings`. Realized against estimated, and the gap between them.

**The objection, and what answers it.** A screen whose main number is usually
smaller than the number promised elsewhere is a screen somebody will ask to have
softened. It is also the only screen in the product that can tell you whether the
product works.

**Acceptance criteria.**

- [ ] Estimated and realized appear under separate headings, never in one row
- [ ] `INCONCLUSIVE` rows are listed with their reason, not hidden
- [ ] The gap is stated in money and is not editorialised
- [ ] A test asserts an `INCONCLUSIVE` row renders

---

### TASK-P3-019: the score screen and the P3 journey

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P3 spec section 9, FEAT-043 |
| Delivers | FEAT-043 |
| Depends on | TASK-P3-016, TASK-P3-018 |
| Estimate | M |

**Goal.** `/waste/score`, and a journey walking recommendation to lifecycle to
realized saving.

**Acceptance criteria.**

- [ ] The components are on the same screen as the score, not behind a link
- [ ] Each component links to the findings that moved it
- [ ] The journey asserts a figure on each of the three screens
- [ ] `make seed` produces a `VERIFIED`, a `REGRESSED` and an `INCONCLUSIVE`
- [ ] `docs/runbooks/demo.md` gains a P3 section

---

### TASK-P3-020: blast radius, which refuses rather than guesses

| Field | Value |
| --- | --- |
| Status | Not started, blocked on P4 |
| Implements | P3 spec section 12, FEAT-044 |
| Delivers | FEAT-044 |
| Depends on | TASK-P3-019, **P4 delivered** |
| Estimate | L |

**Goal.** A score from walking P4's edges outward from a target, and a refusal
where the graph is not known to be complete.

**The objection, and what answers it.** A score that is sometimes absent is less
useful than one always present, and that is exactly the trade being made. An
absent score reads as "we do not know". A low score computed from a graph missing
a region reads as "this change is safe", which is a claim the product would be
making on its own initiative about somebody's production estate.

**Acceptance criteria.**

- [ ] The score walks `topology_edge` outward with a bounded depth
- [ ] It returns **no score and a reason** where `graph_coverage` for the
      resource's account or region is `PARTIAL` or `UNREAD`
- [ ] A test removes one region's edges, marks the slice `PARTIAL`, and requires a
      refusal. It is watched failing with the check removed
- [ ] The screen says the score is a lower bound, because application level
      dependencies are invisible to an infrastructure graph
- [ ] No write path is created. Constraint 6

**Deliberately not in this task.** Automatic application of anything. The gate is
built before the thing it gates, and that is the order on purpose.

---

## What this plan does not answer

**ISS-122 is unchanged.** Every adapter here is written against documentation and
proved against a fake. None of the exit criteria in spec section 15 has been met
against a real estate, and the first real account will produce a list of defects
in TASK-P3-004 and TASK-P3-007 before it produces a recommendation.

**OPEN-03 and OPEN-05 remain open.** Neither blocks this plan. OPEN-03 removes one
check from TASK-P3-004; OPEN-05 adds one adapter task after TASK-P3-011.

**The ticketing adapter is not among the 20 tasks.** It is one task, written when
OPEN-05 is answered, against the port TASK-P3-011 builds.
