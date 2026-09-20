# P6 Containers, EKS and ECS: implementation plan

Date: 2026-09-20
Status: Provisional, pending approval of `docs/specs/2026-09-20-p6-containers-design.md`
Spec: `docs/specs/2026-09-20-p6-containers-design.md`
Depends on: P0 delivered, P1 delivered, P3 delivered
Tasks: 12 in the first cut

The **first cut** is tasks 001 to 012 and measures: what each namespace cost, and
how much of what it reserved it used. The **second cut** is FEAT-047 and FEAT-048,
and it is not planned here. Spec section 3 says why, and the short version is that
an optimiser fed by figures nobody has seen yet produces confident answers that
are wrong.

## How to work this plan

Same contract as P0 through P5. One task, one commit.

**Four rules specific to P6.**

1. **Pod cost is measured, not apportioned.** It arrives as extra columns on the
   billing export already being read, so TASK-P6-002 widens the existing cost
   ingest rather than adding a collector. A product dividing cluster cost itself
   would be producing a modelled figure on every screen that showed it.

2. **Container recommendations are P3 recommendations.** Same table, same
   lifecycle, same severity from the same money. There is no second list. A task
   finding itself creating one has found a disagreement with the spec.

3. **A signal Container Insights cannot supply is named, not approximated.** Spec
   section 5.4. The OOMKilled gap is the one that changes a recommendation, and
   TASK-P6-007 puts the admission in the rationale rather than in a document
   nobody reads at three in the afternoon.

4. **`forecast` exists before anything forecasts.** ADR-0015 condition 4 needs a
   third provenance value beside `measured` and `modelled`, and it touches the
   `Figure` component every screen shares. TASK-P6-012 does it in the first cut so
   the vocabulary is there before the second cut needs it.

## Wave overview

| Wave | Tasks | Delivers | Can start when |
| --- | --- | --- | --- |
| A. Cost from the bill | 001 to 003 | Pod, namespace and workload cost, measured | P1 delivered |
| B. Telemetry | 004 to 006 | Requested against used, and what could not be read | A |
| C. Sizing | 007 to 008 | The two rules, and Fargate sizes that can be ordered | B, P3 delivered |
| D. Surface | 009 to 011 | The guard, the routes and the screens | C |
| E. Vocabulary | 012 | `forecast` as a third provenance, before it is needed | D |

---

### TASK-P6-001: the entities, and a cluster slice that can be unknown

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P6 spec section 4 |
| Delivers | Part of FEAT-036 |
| Depends on | P1 delivered |
| Estimate | M |

**Goal.** `finops_core/domain/containers.py`. `Workload`, `ClusterSlice`,
`ReservationVsUse`.

**Acceptance criteria.**

- [ ] `was_oom_killed` is a three state value, not a boolean. True, false and
      unobserved are three different facts, and a boolean can carry two
- [ ] A reservation with no observed use has no efficiency figure, rather than an
      efficiency of zero
- [ ] Below 14 observation days no recommendation can be constructed, sharing
      `MINIMUM_HISTORY` with P3 and the anomaly detector rather than redefining it
- [ ] Inherits `Fact`

---

### TASK-P6-002: pod cost, which is already in the bill

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P6 spec section 5.1, FEAT-035 |
| Delivers | Part of FEAT-035 |
| Depends on | TASK-P6-001 |
| Estimate | L |

**Goal.** Widen `cost_focus_daily` and the CUR read with the split cost allocation
columns. Migration `0013_split_cost_allocation.py`.

**The objection, and what answers it.** This looks like it belongs in P1, and in a
sense it does: it is P1's collector reading more columns. It is here because the
columns only mean anything to somebody asking a container question, and because
ISS-003 is a prerequisite P1 never needed.

**Acceptance criteria.**

- [ ] Columns added, nullable, backward compatible. Every existing row keeps
      working with nulls, constraint 12
- [ ] The Athena adapter reads them where present and does not fail where absent
- [ ] Pod cost sums to the same period total as `/cost/summary`, asserted, because
      a split that does not reconcile is a split that invented money
- [ ] An export without split cost allocation data enabled produces a **named
      gap**, not clusters costing nothing. ISS-003

---

### TASK-P6-003: the cluster cost read and its screen slice

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P6 spec section 8, FEAT-035 |
| Delivers | FEAT-035 |
| Depends on | TASK-P6-002 |
| Estimate | M |

**Goal.** `GET /containers/cost`, grouped by cluster, namespace and workload.

**Acceptance criteria.**

- [ ] Uses the existing cost guard and the existing repository, not a second read
      path
- [ ] A cluster with no split data is listed with its total and without its
      breakdown, and says which
- [ ] Scoped: a narrow reader sees fewer clusters, asserted
- [ ] The measure is labelled measured, using the existing `Figure` provenance

---

### TASK-P6-004: Container Insights, and the four things it will not tell us

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P6 spec sections 4 and 5.4, FEAT-036 |
| Delivers | Part of FEAT-036 |
| Depends on | TASK-P6-001 |
| Estimate | L |

**Goal.** `finops_providers/aws/container_insights.py`, batched like the P3 metric
reads.

**The objection, and what answers it.** An agent would give more. Spec section 6
records why there is not one, and this file's docstring carries the four line
summary so the next reader does not have to go looking.

**Acceptance criteria.**

- [ ] Batched at 500 metrics per call at a one hour period, as P3's waste adapter
      is, and for the same billing reason
- [ ] A cluster without enhanced observability yields usage and **no request**,
      reported as unavailable rather than as a request of zero
- [ ] `was_oom_killed` is set to unobserved, never to false, because Container
      Insights does not reliably report it
- [ ] Never run against AWS, stated in the first line, ISS-122
- [ ] Held to a contract suite alongside the fake

---

### TASK-P6-005: a fake cluster with a namespace nobody can measure

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P6 spec section 11 |
| Delivers | Part of FEAT-036 |
| Depends on | TASK-P6-004 |
| Estimate | M |

**Goal.** `finops_providers/fake/containers.py`.

**Acceptance criteria.**

- [ ] Two clusters, one with enhanced observability and one without, so both paths
      run in every test above the provider
- [ ] One workload that has been OOMKilled, one whose OOM status is unobserved, and
      one that has not, so all three states are exercised
- [ ] One namespace requesting five times what it uses, which is the finding the
      screen exists for
- [ ] One namespace correctly sized, so a detector that flags everything fails
- [ ] Sized from the estate rather than written down, as the commitment fake is

---

### TASK-P6-006: the usage collector

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P6 spec sections 5.2 and 7, FEAT-036 |
| Delivers | Part of FEAT-036 |
| Depends on | TASK-P6-005 |
| Estimate | M |

**Goal.** `finops_ingest/collectors/container_usage.py`, `container_usage`, and the
schedule row. Migration `0014_container_usage.py`.

**Acceptance criteria.**

- [ ] A check constraint that a request of zero cannot coexist with a positive use,
      since that combination means the request was unread rather than zero
- [ ] `was_oom_killed` nullable, and null means unobserved
- [ ] A cluster that could not be read is recorded as such, not omitted
- [ ] One cluster failing does not fail the run

---

### TASK-P6-007: two sizing rules, and the one that admits it could not check

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P6 spec sections 5.3 and 5.4, FEAT-036 |
| Delivers | FEAT-036 |
| Depends on | TASK-P6-006, P3 delivered |
| Estimate | L |

**Goal.** `finops_query/containers.py`, writing into P3's `recommendation` table.

**The objection, and what answers it.** Sizing memory at peak plus 15 percent for a
workload whose OOM history is unknown is the safe looking choice and is not safe:
the workloads that have been killed are exactly the ones needing the larger margin,
and treating unknown as "not killed" applies the smaller one to them silently. The
rule is unchanged; the rationale says the check could not be made.

**Acceptance criteria.**

- [ ] CPU at the 99th percentile of the max rate, memory at peak plus 15 percent,
      plus 25 percent where OOMKilled is **true**
- [ ] Where OOMKilled is **unobserved**, the 15 percent rule applies and the
      rationale says so in words. A test reads the rationale, not the number
- [ ] Recommendations are written to P3's table with a container waste class,
      inheriting its lifecycle and its severity
- [ ] No second recommendation table is created, asserted by a test that counts
      them

---

### TASK-P6-008: Fargate sizes somebody can actually order

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P6 spec section 5.5, FEAT-037 |
| Delivers | FEAT-037 |
| Depends on | TASK-P6-007 |
| Estimate | M |

**Goal.** ECS and Fargate task sizing, snapped up to the valid vCPU and memory
matrix.

**The objection, and what answers it.** Snapping up reduces the estimated saving,
and reporting the unsnapped saving would look better. It would also be a number
nobody can realise, and the first person to try would stop believing the rest of
the screen.

**Acceptance criteria.**

- [ ] Every recommendation is a valid Fargate combination, asserted against the
      matrix
- [ ] Snapping is always up. A test tries a size that would snap down and fails
- [ ] The estimated saving is computed from the snapped size, not the ideal one
- [ ] The matrix is a table in code with a source comment, not scattered literals

---

### TASK-P6-009: the guard, then the routes

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P6 spec section 8, constraint 3 |
| Delivers | Part of FEAT-036 |
| Depends on | TASK-P6-008 |
| Estimate | M |

**Goal.** `container_usage` in `SCOPED_TABLES`, then the three routes.

**Acceptance criteria.**

- [ ] `ByAccount("sub_account_id")`, because a cluster lives in an account
- [ ] A test reads out of scope and is refused, before a route exists
- [ ] The coverage figure counts clusters measured against clusters found, with a
      `coverage_unit` saying so
- [ ] Every route returns the envelope

---

### TASK-P6-010: request and use as two figures

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P6 spec section 9, FEAT-036 |
| Delivers | Part of FEAT-036 |
| Depends on | TASK-P6-009 |
| Estimate | M |

**Goal.** `/containers/usage`.

**The objection, and what answers it.** One efficiency percentage per namespace
would fit the screen better. A namespace at 20 percent could be over requesting by
a factor of five or could be idle, and those are different conversations with
different people. The two figures stay two figures.

**Acceptance criteria.**

- [ ] Request and use are separate columns, never one percentage
- [ ] A cluster without enhanced observability appears with its cost and without
      its utilization, and names the reason
- [ ] `arrives` cleared in `sections.ts`
- [ ] No accessibility violations

---

### TASK-P6-011: the cost and cluster screens, and the journey

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P6 spec section 9, FEAT-035, FEAT-037 |
| Delivers | FEAT-035, FEAT-037 |
| Depends on | TASK-P6-010 |
| Estimate | L |

**Goal.** `/containers/cost`, `/containers/clusters`, and the P6 journey.

**Acceptance criteria.**

- [ ] Namespace cost reconciles visibly to the cluster total on screen
- [ ] Spot ratio and bin packing are shown per cluster
- [ ] The journey asserts a figure on each screen and asserts the unmeasurable
      cluster is named
- [ ] `make seed` produces both clusters, all three OOM states, and one container
      recommendation in P3's list
- [ ] `docs/runbooks/demo.md` gains a P6 section saying which cluster is
      deliberately unmeasurable and why

---

### TASK-P6-012: a third word for a number

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P6 spec section 14, ADR-0015 condition 4 |
| Delivers | Nothing visible. It makes the second cut possible |
| Depends on | TASK-P6-011 |
| Estimate | M |

**Goal.** `forecast` as a third provenance value beside `measured` and `modelled`,
through the domain, the schemas, the `Figure` component and every screen rendering
one.

**The objection, and what answers it.** Adding a vocabulary for something nothing
produces yet is exactly the speculative generality this project avoids. It is here
for one reason: it is a cross cutting change to a component every screen shares,
and doing it inside the task that first needs it means a forecasting feature also
carrying a refactor of the whole interface. ADR-0015 condition 4 makes it mandatory
whenever FEAT-048 ships, so the only question is whether it lands alone or lands
tangled.

**Acceptance criteria.**

- [ ] `forecast` renders distinctly from both existing values, and a test asserts
      all three are distinguishable
- [ ] Nothing produces a `forecast` yet, and a test asserts that too, so the value
      cannot be quietly used before its four conditions are met
- [ ] ADR-0015 is referenced at the definition
- [ ] `make verify` passes with no screen changing its appearance

---

## The second cut

FEAT-047 and FEAT-048, planned when the first cut has produced data worth
optimising against, and specified in a later section of the P6 design document at
that point.

Two things will already be true when that happens, and they are here so the second
cut starts from them rather than rediscovering them.

**FEAT-047 needs a solver**, which is a new dependency and goes through
`make dep-check` like any other. An integer linear program is also the first thing
in this product whose output a reader cannot check by hand, so it will need the
treatment ADR-0016 gave severity: the inputs, the constraints and the chosen mix
all visible beside the answer.

**FEAT-048 needs all four ADR-0015 conditions**, and TASK-P6-012 delivers the
fourth. The other three are a backtest published in the product, an error bound on
every forecast, and a deterministic fallback to the p95 rule when accuracy falls
below a stated floor. None is optional, and none is a second cut acceptance
criterion to soften.

---

## What this plan does not answer

**ISS-003.** Split cost allocation data has never been enabled, so FEAT-035 has no
data. TASK-P6-002 reports its absence by name rather than as zero, and the rest of
the first cut is unaffected.

**ISS-122.** Neither adapter has run.

**Whether the agent decision was right.** Spec section 5.4 states the cost of it
per signal, and TASK-P6-007 puts the largest consequence into the rationale of
every affected recommendation. When somebody wants to revisit it, the evidence is
already in the product rather than in a memory of a conversation.
