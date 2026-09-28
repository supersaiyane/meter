# P5 Quotas and Limits: implementation plan

Date: 2026-09-20
Status: Provisional, pending approval of `docs/specs/2026-09-20-p5-quotas-and-limits-design.md`
Spec: `docs/specs/2026-09-20-p5-quotas-and-limits-design.md`
Depends on: P0 delivered
Tasks: 8

The smallest sub project in the roadmap, and the one whose central decision is
about what the product refuses to do. See spec section 6.

## How to work this plan

Same contract as P0 through P4. One task, one commit.

**Three rules specific to P5.**

1. **A quota with no usage source is never zero.** Spec section 5.2. The database
   refuses it, the screen says it, and TASK-P5-002 writes the constraint before
   TASK-P5-004 writes a collector that could violate it.

2. **Nothing submits a quota increase.** Constraint 6, decided 2026-09-20 as track
   only. The IAM permission is deliberately absent, and TASK-P5-007 writes a test
   naming the API, so a future contributor adding it fails a test that explains
   why.

3. **The guard before the route**, as in every plan since ISS-184.

## Wave overview

| Wave | Tasks | Delivers | Can start when |
| --- | --- | --- | --- |
| A. Domain and schema | 001 to 002 | The widened entity and the two tables | P0 delivered |
| B. Providers | 003 | Four sources, and the honest gaps between them | A |
| C. Ingest | 004 | Every quota, including the ones nothing can measure | B |
| D. Surface | 005 to 006 | The guard, the routes, and the two list screen | C |
| E. The refusal | 007 to 008 | The tracking, and the test that keeps the write out | D |

---

### TASK-P5-001: the entity that already knew

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-28 |
| Implements | P5 spec section 4, FEAT-033 |
| Delivers | Part of FEAT-033 |
| Depends on | P0 delivered |
| Estimate | S |

**Goal.** Widen `finops_core/domain/quota.py`. `QuotaUsage` already exists from P0
and already says unpublished usage is None rather than zero; this adds
`usage_source`, `is_adjustable` and the headroom property.

**The objection, and what answers it.** None, and that is worth noticing. P0 got
this right, and the only thing P5 adds is the field recording which of four
sources the usage came from. The rest of this sub project is downstream of a
decision already made.

**Acceptance criteria.**

- [ ] `headroom` returns None where `used_value` is None, never a fraction
- [ ] A `usage_source` of `NONE` with a usage figure cannot be constructed
- [ ] A usage above the limit cannot be constructed
- [ ] Inherits `Fact`

---

### TASK-P5-002: the constraint that does the work

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-28 |
| Implements | P5 spec sections 5.1 and 5.3 |
| Delivers | Part of FEAT-033 |
| Depends on | TASK-P5-001 |
| Estimate | M |

**Goal.** `migrations/versions/0012_quotas.py`. `quota_usage` and `quota_request`.

**The objection, and what answers it.** The `usage_source = 'NONE'` if and only if
`used_value IS NULL` constraint looks like belt and braces over an application
rule. Constraint 11 says application code is not what should prevent a bad row,
and this is the specific bad row that matters: a usage figure with no provenance
cannot be audited later, and it renders identically to one that was measured.

**Acceptance criteria.**

- [ ] The biconditional constraint exists and is watched refusing both directions:
      a source with no usage, and a usage with no source
- [ ] `used_value <= limit_value` where both are present
- [ ] `quota_request` has no application write path, matching spec section 6
- [ ] Backward compatible, constraint 12

---

### TASK-P5-003: four sources and the gaps between them

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-28 |
| Implements | P5 spec section 5.2, FEAT-033 |
| Delivers | Part of FEAT-033 |
| Depends on | TASK-P5-002 |
| Estimate | L |

**Goal.** `finops_providers/aws/quotas.py`. Service Quotas for limits, `AWS/Usage`
for the subset that publishes usage, Trusted Advisor where the support tier
allows, service specific calls for the few that have them.

**Acceptance criteria.**

- [ ] Every quota Service Quotas returns produces a row, whether or not usage can
      be found for it
- [ ] A quota with no usage source sets `usage_source` to `NONE` and leaves
      `used_value` null. It is **not** omitted
- [ ] Trusted Advisor absence under a support tier without it is `NotOptedIn` and
      reduces coverage rather than producing an error
- [ ] Never run against AWS, stated in the first line, ISS-122
- [ ] Held to a contract suite alongside the fake

---

### TASK-P5-004: the collector, and a fake with holes in it

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P5 spec sections 7 and 11, FEAT-033 |
| Delivers | FEAT-033 |
| Depends on | TASK-P5-003 |
| Estimate | M |

**Goal.** `finops_ingest/collectors/quotas.py`, its schedule row, and a fake
estate where several quotas cannot be measured.

**Acceptance criteria.**

- [ ] The fake has unmeasurable quotas in roughly the proportion a real estate
      does, not one token example
- [ ] A second run over an unchanged estate leaves the row count unchanged
- [ ] A quota that had usage and now has none writes a null and changes its source,
      rather than keeping the stale figure
- [ ] Twelve hourly, with the reason and cost in `collector_schedule`, ADR-0012
- [ ] One account failing does not fail the run

---

### TASK-P5-005: the guard, then the routes

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P5 spec section 8, constraint 3 |
| Delivers | Part of FEAT-033 |
| Depends on | TASK-P5-004 |
| Estimate | M |

**Goal.** `quota_usage` and `quota_request` in `SCOPED_TABLES`, then the three
routes.

**Acceptance criteria.**

- [ ] Both are `ByAccount("sub_account_id")`, because a quota is per account per
      region
- [ ] A test reads each out of scope and is refused, before a route exists
- [ ] Every route returns the envelope
- [ ] The coverage figure counts **quotas measured against quotas found**, not
      accounts, and passes a `coverage_unit` saying so. This would be the fourth
      time a wrong count reached that slot; see `tasks/lessons.md`

---

### TASK-P5-006: two lists, because one would lie

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P5 spec section 9, FEAT-033 |
| Delivers | FEAT-033 |
| Depends on | TASK-P5-005 |
| Estimate | M |

**Goal.** `/governance/quotas`. Measurable quotas sorted by headroom, unmeasurable
ones listed separately with their reason.

**The objection, and what answers it.** One list with a blank column would be
simpler and is what most tools do. A blank sorts somewhere, and wherever it sorts
is a claim: at the top it looks urgent, at the bottom it looks safe. Neither is
known. Two lists is the only arrangement that does not imply an ordering nobody
has earned.

**Acceptance criteria.**

- [ ] Two lists under two headings, and the unmeasurable one names its reason per
      quota
- [ ] The count of each is stated, because the ratio is the honest summary of how
      much of this problem AWS lets anybody solve
- [ ] A quota at 90 percent of its limit is visually distinct from one at 10
- [ ] `arrives` cleared in `sections.ts`
- [ ] No accessibility violations

---

### TASK-P5-007: the draft, and the test that keeps the write out

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P5 spec section 6, FEAT-034 |
| Delivers | Part of FEAT-034 |
| Depends on | TASK-P5-006 |
| Estimate | M |

**Goal.** A drafted increase, a console link, a CLI command, and a test asserting
nothing calls `RequestServiceQuotaIncrease`.

**The objection, and what answers it.** Drafting a request and then asking a human
to paste it is worse for the human than doing it. It is, by exactly one paste, and
it buys the sentence "this product has never written into a customer account",
which is worth more than one paste. Spec section 6 argues it properly.

**Acceptance criteria.**

- [ ] The draft shows the current limit, the observed usage and the suggested value
      with its working
- [ ] The console link and the CLI command are both exact and both copyable
- [ ] The screen says Meter will not submit it, and why, in one sentence
- [ ] A test searches the source for `RequestServiceQuotaIncrease` and fails if it
      appears outside a comment or a test. The test name explains the decision
- [ ] The org reader IAM policy does not grant it, asserted against the Terraform

---

### TASK-P5-008: tracking what somebody else submitted

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P5 spec section 5.3, FEAT-034 |
| Delivers | FEAT-034 |
| Depends on | TASK-P5-007 |
| Estimate | M |

**Goal.** Read `ListRequestedServiceQuotaChangeHistory`, write `quota_request`, and
show outstanding requests with their status.

**The objection, and what answers it.** This is the half of FEAT-034 actually
missing today. Nobody loses a quota increase because they could not find the
button. They lose it because nobody checked whether it was ever approved.

**Acceptance criteria.**

- [ ] A request made outside Meter appears within one collection cycle
- [ ] Status transitions are visible, including `DENIED`, which is the one a
      product is tempted to hide
- [ ] A request whose quota Meter cannot measure still tracks. The two features are
      independent
- [ ] The P5 journey walks quota to draft to tracked request
- [ ] `docs/runbooks/demo.md` gains a P5 section saying the draft is not submitted

---

## What this plan does not answer

**ISS-122.** The adapter has never run. Service Quotas pagination and the
`AWS/Usage` metric names are the parts a real account will correct first.

**OPEN-03.** Without Business or Enterprise support, Trusted Advisor contributes
nothing and the measurable list is smaller. Nothing breaks; the ratio in
TASK-P5-006 simply reads worse, which is accurate.

**Whether track only survives contact with users.** If enough people ask Meter to
submit the request, that is a decision to reopen with an ADR superseding constraint
6, not a thing to slip in. Spec section 6 exists so that conversation starts from
the reasoning rather than from scratch.
