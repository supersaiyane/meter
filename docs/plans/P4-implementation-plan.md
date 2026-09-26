# P4 Inventory and Topology: implementation plan

Date: 2026-09-20
Status: Provisional, pending approval of `docs/specs/2026-09-20-p4-inventory-and-topology-design.md`
Spec: `docs/specs/2026-09-20-p4-inventory-and-topology-design.md`
Depends on: P0 delivered
Tasks: 11

What is out there, and what is connected to what. Three features, and one rule
that shapes all of them: an edge Meter cannot see is not an absent edge.

## How to work this plan

Same contract as P0, P1, P2 and P3. One task, one commit.

**Four rules specific to P4.**

1. **Incompleteness is data, not an error path.** A failed cost collection leaves
   a missing number and a screen that says so. A failed topology collection leaves
   a graph that still renders, still traverses, and answers every question wrongly
   in the same direction. `graph_coverage` is written on every run including
   failed ones, and TASK-P4-005 builds it before any consumer exists.

2. **The fake estate is incomplete by default.** Three regions, one of which
   refuses. Every test above the provider therefore runs against a partial graph
   unless it deliberately asks otherwise. A fake that is whole by default makes
   the incompleteness path the one nobody exercises, and that path is the point of
   this sub project.

3. **Traversal is bounded, server side.** Depth and node count. An unbounded
   traversal of a real estate returns the estate, and the browser is not where
   that should be discovered.

4. **Config costs money and the number is written down before it is applied.**
   ISS-012. TASK-P4-010 carries the estimate, and constraint 7 means the actual
   figure lands on our own platform cost screen afterwards.

## Wave overview

| Wave | Tasks | Delivers | Can start when |
| --- | --- | --- | --- |
| A. Domain and schema | 001 to 002 | Nodes, edges, coverage, and the tables | P0 delivered |
| B. Providers | 003 to 004 | The Config aggregator and the relationships Config does not give | A |
| C. Ingest and coverage | 005 to 006 | Rows, and the truthful record of what was not read | B |
| D. Traversal | 007 | Recursive, bounded, returning its own coverage | C |
| E. Interface | 008 to 009 | Three routes and the map | D |
| F. Infrastructure | 010 | Terraform that validates, is not applied, and states its cost | A |
| G. Proof | 011 | The journey, and the test every consumer must pass | E |

---

### TASK-P4-001: nodes, edges, and a coverage that can say unread

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-26 |
| Implements | P4 spec section 5, FEAT-030, FEAT-031 |
| Delivers | Part of FEAT-031 |
| Depends on | P0 delivered |
| Estimate | M |

**Goal.** `finops_core/domain/topology.py`. `Node`, `Edge`, `NodeKind`,
`EdgeKind`, `GraphCoverage`.

**The objection, and what answers it.** `GraphCoverage` with three states looks
like one too many: complete or not seems enough. `UNREAD` is the state a slice is
in before anything has tried, and it differs from `PARTIAL` in the way that
matters. A slice nobody attempted and a slice that refused us are both unsafe to
score against, but only one of them is a fault somebody should fix.

**Acceptance criteria.**

- [ ] `availability_zone` is nullable, and the docstring says a null means a
      regional resource rather than an unknown one
- [ ] `Edge` is directed, and a test asserts that reversing it is a different edge
- [ ] `GraphCoverage` carries a typed cause when not `COMPLETE`
- [ ] Both timestamps, inheriting `Fact`

---

### TASK-P4-002: three tables and the constraints that keep them honest

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-26 |
| Implements | P4 spec section 5 |
| Delivers | Part of FEAT-030 |
| Depends on | TASK-P4-001 |
| Estimate | M |

**Goal.** `migrations/versions/0011_topology.py`. `topology_node`,
`topology_edge`, `graph_coverage`.

**Acceptance criteria.**

- [ ] `topology_edge` unique on `(tenant_id, from_node_id, to_node_id, edge_kind)`
- [ ] `graph_coverage` unique on `(tenant_id, sub_account_id, region_id)`, so a
      slice has exactly one current state
- [ ] A check that `state` is `COMPLETE`, `PARTIAL` or `UNREAD`, and that a
      `cause` is present whenever the state is not `COMPLETE`. The second is the
      constraint that stops a partial slice being recorded without a reason
- [ ] Indexes supporting outward traversal from a node, which is the only shape
      the graph is ever read in
- [ ] Backward compatible, constraint 12

---

### TASK-P4-003: the Config aggregator, unproved

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-26 |
| Implements | P4 spec section 4, FEAT-030 |
| Delivers | Part of FEAT-030 |
| Depends on | TASK-P4-002 |
| Estimate | L |

**Goal.** `finops_providers/aws/config_inventory.py`. Resources and their
relationships from an organization aggregator.

**Acceptance criteria.**

- [ ] Paginated, every page, with the same bounded retry the other adapters use
- [ ] A region that refuses produces a typed cause and **does not** shorten the
      result silently. The caller learns which region and why
- [ ] Relationship records are parsed into edges with `source` set to
      `CONFIG_RELATIONSHIP`
- [ ] **Never run against AWS**, stated in the first line, naming the resource
      types the mapping is least sure about
- [ ] Held to the contract suite

---

### TASK-P4-004: the edges Config does not give you

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-26 |
| Implements | P4 spec section 4, FEAT-031 |
| Delivers | Part of FEAT-031 |
| Depends on | TASK-P4-003 |
| Estimate | L |

**Goal.** `finops_providers/aws/topology.py`. Transit Gateway attachments, VPC
peering, PrivateLink, cross account trust.

**The objection, and what answers it.** Config supplies most relationships, so
this looks like completing a long tail for little value. The long tail is where
the cross account edges are, and a blast radius score that stops at the account
boundary is the one most likely to be confidently wrong.

**Acceptance criteria.**

- [ ] Every edge carries the API that supplied it in `source`, so a future reader
      knows which edges depend on this file
- [ ] `is_cross_account` is set at write time, not computed on read
- [ ] A partial read of one edge kind does not discard the others, and each
      contributes to the coverage record separately
- [ ] Never run against AWS, and says so

---

### TASK-P4-005: the record of what was not read

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-26 |
| Implements | P4 spec section 6 |
| Delivers | Part of FEAT-030 |
| Depends on | TASK-P4-002 |
| Estimate | M |

**Goal.** The coverage collector, and the rule that it writes on every run.

**The objection, and what answers it.** This could be derived: a slice with no
nodes was presumably not read. It could not, and the difference is the sub
project. An account with genuinely no resources in a region and an account whose
region refused us look identical by row count, and only one of them is safe to
score against.

**Acceptance criteria.**

- [ ] A row is written for every account and region on every run, including runs
      that failed entirely
- [ ] A slice never attempted has an `UNREAD` row, created when the account is
      enrolled rather than when a collection first fails
- [ ] A slice that succeeded after failing moves back to `COMPLETE`, and a test
      asserts the transition in both directions
- [ ] The row carries the typed cause, not a message

---

### TASK-P4-006: the collectors

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-26 |
| Implements | P4 spec section 7, FEAT-030, FEAT-031 |
| Delivers | FEAT-030 |
| Depends on | TASK-P4-004, TASK-P4-005 |
| Estimate | L |

**Goal.** `finops_ingest/collectors/inventory.py` and `topology.py`, with their
schedule rows.

**Acceptance criteria.**

- [ ] A resource that has gone is removed, and its edges with it, scoped to one
      tenant and one run, using the same pattern `cost_focus` uses
- [ ] A half read removes nothing, because the transaction rolls back and the
      removal sits downstream of finishing the read
- [ ] One account failing never fails the run, and the failure reaches
      `graph_coverage` and `sync_error` both
- [ ] The schedule rows carry their reason and their cost

---

### TASK-P4-007: traversal that carries its own coverage

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-26 |
| Implements | P4 spec sections 6 and 8, FEAT-031 |
| Delivers | FEAT-031 |
| Depends on | TASK-P4-006 |
| Estimate | L |

**Goal.** `finops_query/graph.py`. A recursive CTE outward from a root, bounded,
returning nodes, edges **and** the coverage of every slice it touched.

**The objection, and what answers it.** Returning coverage alongside the result
makes every caller handle a second value they mostly do not want. That is the
intent. An optional coverage lookup is one a caller forgets, and the caller who
forgets is FEAT-044, scoring somebody's production change.

**Acceptance criteria.**

- [ ] Coverage is part of the return type, not a separate call
- [ ] A cycle terminates. A security group referencing itself is the test case
- [ ] Depth is bounded and the bound is a parameter with a default, not a literal
- [ ] Node count is capped, and hitting the cap is reported rather than silent
- [ ] No `boto3`, no `datetime.now`, and the guard's own `scoped_select` is used
      rather than a hand rolled select

---

### TASK-P4-008: the guard, then the routes

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-26 |
| Implements | P4 spec section 8, constraint 3 |
| Delivers | Part of FEAT-032 |
| Depends on | TASK-P4-007 |
| Estimate | M |

**Goal.** `topology_node`, `topology_edge` and `graph_coverage` in
`SCOPED_TABLES`, then the three routes.

**Acceptance criteria.**

- [ ] `topology_node` is `ByAccount("sub_account_id")`
- [ ] `topology_edge` has its rule argued in a comment, because an edge joins two
      nodes that may be in different accounts, and a cross account edge visible to
      a reader entitled to only one end is a decision rather than an oversight
- [ ] A test reads each table out of scope and is refused, before any route exists
- [ ] The subgraph response carries coverage in the envelope
- [ ] The coverage banner counts the right unit, asserted against another route

---

### TASK-P4-009: the map, and what it admits

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-26 |
| Implements | P4 spec section 9, FEAT-032 |
| Delivers | FEAT-032 |
| Depends on | TASK-P4-008 |
| Estimate | L |

**Goal.** `/inventory/topology`, Cytoscape.js, capped at 2,000 nodes server side.

**Acceptance criteria.**

- [ ] A region with `PARTIAL` coverage is named above the graph, not in a footnote
- [ ] A truncated subgraph says so and says how many nodes were omitted
- [ ] The cap is enforced by the route. A test calls the route with a root that
      would exceed it and asserts the truncation is reported
- [ ] `arrives` cleared in `sections.ts`
- [ ] No accessibility violations, and a keyboard alone reaches the graph, as the
      organization map already proves is possible

---

### TASK-P4-010: Terraform that states its own cost

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-26 |
| Implements | P4 spec section 10, ISS-012 |
| Delivers | Part of FEAT-030 |
| Depends on | TASK-P4-001 |
| Estimate | L |

**Goal.** `infra/terraform/config/`. The aggregator in the payer account, the
recorders as a member StackSet, selective by resource type.

**The objection, and what answers it.** ISS-012 says organization wide Config
recording is a five figure monthly line item, and this task is where that either
becomes a decision or becomes a surprise. Selective recording was decided on
2026-09-20.

**Acceptance criteria.**

- [ ] The recorded resource type list is in Terraform, reviewable in a diff, not
      in prose
- [ ] **The task carries the estimated monthly cost**, with the resource type
      count and the assumed configuration item volume that produced it. A number
      with no working is not an estimate
- [ ] Recorders are tagged `finops:module`, constraint 7, so the real figure
      reaches our own cost screen and can be compared with the estimate above
- [ ] `terraform validate` and `fmt -check` pass on all stacks
- [ ] **Nothing is planned and nothing is applied**, and that is what done means
      for this task rather than a caveat on it. ISS-122

---

### TASK-P4-011: the test every consumer has to pass

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-26 |
| Implements | P4 spec section 6, exit criterion 6 |
| Delivers | FEAT-031 |
| Depends on | TASK-P4-009 |
| Estimate | M |

**Goal.** The contract test that removes a region's edges, marks the slice
`PARTIAL`, and requires every consumer to refuse rather than answer. Plus the P4
journey.

**The objection, and what answers it.** This looks like a test for a consumer that
does not exist yet, since FEAT-044 is in P3 and comes after. Writing it here is
the point: the rule belongs to the graph, and the first consumer to arrive should
find the test already waiting rather than be trusted to remember.

**Acceptance criteria.**

- [ ] The test is parameterised over consumers, and adding one without handling
      `PARTIAL` fails it
- [ ] It is watched failing with the coverage check removed
- [ ] The journey walks the map, opens a truncated subgraph, and asserts both the
      truncation notice and the partial region notice
- [ ] `make seed` produces an estate with one unreadable region
- [ ] `docs/runbooks/demo.md` gains a P4 section saying which region is
      deliberately unreadable and why

---

### TASK-P4-012: the resource list, which the navigation has promised since P4 began

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | ISS-204. Competitive review 2026-09-26, no resource list |
| Delivers | FEAT-056 |
| Depends on | TASK-P4-008 delivered |
| Estimate | M |

**Goal.** `/inventory/resources`. Every resource this scope can see, filterable by
account, region, kind and resource type, each row linking to the entity page
FEAT-053 built.

**This closes ISS-204 rather than working around it.** The navigation has promised
this screen since P4 started and the P4 specification never scheduled one, so a
delivered sub project was named as the thing that would bring a screen nobody
planned. Adding the task is one of the two closures ISS-204 names, and it is the
one that does not involve editing a marker to make an inconsistency disappear.

**The objection, and what answers it.** We built a map so a list looks like a step
backwards. The map answers what is connected to what for one root, bounded to four
hops. It cannot answer "how many gp2 volumes do I have in Frankfurt", which is the
question somebody actually arrives with, and orientation is the gap the competitive
review names twice.

**The failure this task exists to avoid.** A list that looks complete. Every row
comes out of a slice, and a slice that refused us contributes nothing while looking
identical to a region that is genuinely empty. The estate wide coverage banner is
already built, FEAT-032, and this screen shows it above the list rather than beside
it. A count at the top of a list is a claim about the estate.

**Acceptance criteria.**

- [ ] Server side pagination and filtering. An estate of three hundred accounts is
      not a list the browser sorts, and TASK-P4-007's bound exists for this reason
- [ ] The coverage banner above the list, not below, and the count says how many
      slices it is drawn from
- [ ] Every row links to `/inventory/resources/:nodeId`, which FEAT-053 built
- [ ] A null region renders as global and a null zone as regional, never as unknown
      or as an empty cell
- [ ] The `arrives` marker for this path in `sections.ts` becomes null in the same
      commit, and `sections.test.ts` passes without its exception
- [ ] One journey: filter to a kind, land on a resource, come back

---

### TASK-P4-013: which file manages this resource

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Competitive review 2026-09-26, candidate list, adopted by the owner on 2026-09-26 |
| Delivers | FEAT-057 |
| Depends on | TASK-P4-002 delivered |
| Estimate | M |

**Goal.** Record, per resource, whether infrastructure as code manages it and
which state file and address own it. Read from Terraform state, attached to
`topology_node`.

**Why it lives in P4 and not in P7 with FEAT-040.** The review lists this as
Terraform state discovery so FEAT-040 knows which file to change, which made it
look like an LLM layer prerequisite. It is not: who manages a resource is an
inventory fact about that resource, and it belongs beside its region and its zone.
FEAT-040 is a consumer. P7 has no plan and no approved specification, and writing
tasks into one would be the guess the plans README warns about.

**The objection, and what answers it.** Reading somebody's Terraform state sounds
like a large new integration. The useful ninety percent is small: state holds a
resource address and a provider identifier, and the identifier is the ARN
`topology_node` already keys on. The hard part is not parsing, it is that state
lives wherever the customer put it.

**The failure this task exists to avoid.** Claiming a resource is unmanaged because
we could not find its state. Unmanaged is an actionable fact and "we did not look
in the right bucket" is not, and rendering the second as the first would tell
somebody to import a resource that is already in a module. So the field is three
valued: managed with an address, unmanaged, or not determined, and not determined
is the default rather than unmanaged.

**Acceptance criteria.**

- [ ] The column is nullable and a null means not determined. A test asserts that
      no code path writes unmanaged when no state was read
- [ ] State is read only, and the backend location is configuration rather than
      discovery. Constraint 6, and guessing at buckets is reconnaissance
- [ ] No credential for a customer state backend is stored in this repository, and
      the scan gate covers the new configuration
- [ ] The entity page shows the address where there is one, and says not determined
      where there is not
- [ ] Backward compatible migration, constraint 12. Add, backfill, then nothing is
      dropped

**Deliberately not in this task.** Writing a pull request, which is FEAT-040, and
reading CloudFormation or CDK. One format first, and the port is shaped so a second
is an adapter.

---

## What this plan does not answer

**ISS-122.** Neither adapter has run. The Config mapping in TASK-P4-003 is the
part a real aggregator will correct first.

**ISS-012 is decided, not closed.** Selective recording is the decision. Whether
the estimate in TASK-P4-010 survives contact with a real estate is unknown, and
the mechanism for finding out is on the platform cost screen.

**OPEN-02, single or multiple payers.** A second payer means a second aggregator
and cross payer edges. The edge model already holds them; the collector does not
fan out across payers, and that is one task when the question is answered.
