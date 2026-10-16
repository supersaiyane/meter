# P16 Costing before deployment: implementation plan

Date: 2026-10-16
Status: Chosen by the owner on 2026-10-16 with OPEN-45 answered; OPEN-44 held, blocking TASK-P16-010 alone. In build
Spec: `docs/specs/2026-10-16-p16-costing-before-deployment-design.md`
Depends on: P4, P9, P10, P12, P13 and P15. Proof against a real repository waits on a GitHub App installation, ISS-300, and on OPEN-44
Tasks: 10

Nobody sees what a Terraform change costs until the bill arrives. This sub project reduces the
plan the organization's own pipeline writes to what sets a price, prices it from P9's catalogue,
writes one comment on the pull request, and a month after the change is applied compares the
estimate with the bill and publishes how close it came.

## How to work this plan

Same contract as P0 through P15. One task, one commit, `make verify` green before a merge into
main, and main pushed after every merge.

**Three rules specific to P16.**

1. **Meter never runs Terraform and never stores a plan.** The pipeline plans; the reduction keeps
   the priced attributes and drops the rest in memory, and a test plants a value in every dropped
   field and finds it nowhere.
2. **A resource not priced has no figure.** It carries its reason and no number, a database check
   holds it, and the unpriced count is shown before the total. Constraint 5.
3. **The estimate is modelled and the bill is measured.** The comment quotes list prices only; the
   comparison shows list and effective cost and publishes accuracy at list.

## Wave overview

| Wave | Tasks | Delivers | Can start when |
| --- | --- | --- | --- |
| A. The design | 001 | The spec, this plan, the register | The owner's go |
| B. Reading and pricing | 002, 003, 004 | A plan reduced; compute, storage and the managed services priced | A |
| C. Storing and saying | 005, 006 | The estimate stored by the collector; the comment written and edited | B |
| D. Against the bill | 007 | Each created resource compared, accuracy published | C |
| E. The screen and the proof | 008, 009 | The routes, the screen, the local stack, the exit criteria | D |
| F. Arrival | 010 | A plan from the pipeline, by the route OPEN-44 chooses | OPEN-44 answered |

Modelled at the pace of P15: six tasks of size M and four of size S, about four working days for
001 to 009.

---

### TASK-P16-001: the spec, the plan and the register

| Field | Value |
| --- | --- |
| Status | Done 2026-10-16 |
| Implements | The whole spec |
| Delivers | The design |
| Depends on | Nothing |
| Estimate | S |

**Acceptance criteria.**

- [x] The spec and this plan, with OPEN-44 held and OPEN-45 answered as the owner said
- [x] FEAT-095 to FEAT-098, P16, OPEN-44, OPEN-45 and the change in the register, each feature with
      its document, and `make verify-docs` green

---

### TASK-P16-002: reading a plan

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec sections 5.2 and 9 |
| Delivers | FEAT-095 |
| Depends on | TASK-P16-001 |
| Estimate | M |

**Acceptance criteria.**

- [ ] A pure function in `finops_query` reduces `terraform show -json` to each managed
      `hashicorp/aws` resource change: address, type, actions, Region, the priced attributes before
      and after, and the names unknown until apply
- [ ] The Region from the resource's own argument, its availability zone, or the provider
      configuration it names, a constant or a variable; none of these is a reason, not a guess
- [ ] Refused with the reason: not a plan, a format whose major version is not 1, over 50 MiB
- [ ] Tested on Terraform 1.x plans with modules, `count`, `for_each` and an aliased provider; a
      value planted in every dropped field is absent from the result

---

### TASK-P16-003: pricing compute and storage

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec sections 5.3 and 5.4 |
| Delivers | FEAT-095 |
| Depends on | TASK-P16-002 |
| Estimate | M |

**Acceptance criteria.**

- [ ] A catalogue port in `finops_core` and its reads beside `catalog_reads.py`, sharing the
      comparable price's filter rather than copying it
- [ ] `aws_instance` priced at its type's hourly price as Linux, with its root and EBS block devices
      as volumes; `aws_ebs_volume` for every volume type's storage, io1 and gp3 IOPS, gp3 throughput
- [ ] Each line keeps its components with unit prices, price identifiers and version, as figures
- [ ] A Region the catalogue lacks, a type it does not sell, an attribute unknown until apply, and
      io2's tiered IOPS each a reason with no figure

---

### TASK-P16-004: pricing the managed services

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 5.3 |
| Delivers | FEAT-095 |
| Depends on | TASK-P16-003 |
| Estimate | M |

**Acceptance criteria.**

- [ ] `aws_db_instance` for MySQL, PostgreSQL and MariaDB, single or Multi-AZ, with storage and
      provisioned IOPS; `aws_rds_cluster_instance` for its class
- [ ] `aws_elasticache_cluster` and `aws_elasticache_replication_group` by node type and count;
      `aws_redshift_cluster` by node type and count; `aws_opensearch_domain` and
      `aws_elasticsearch_domain` for data, master and warm instances and EBS per data node
- [ ] Oracle, SQL Server, Aurora storage, RA3 managed storage and every other type named with its
      reason
- [ ] Tested against the real price list rows P9's tests hold, for every line and every reason

---

### TASK-P16-005: storing estimates, the `plan_estimates` collector

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec sections 5.7, 5.8, 6 and 7 |
| Delivers | FEAT-095 |
| Depends on | TASK-P16-004 |
| Estimate | M |

**Acceptance criteria.**

- [ ] A migration for `terraform_plan`, `planned_change`, `plan_estimate` and `plan_estimate_line`,
      with the check that a line not priced carries no figure, and the collector's cadence for
      existing tenants
- [ ] The collector prices each plan received and writes its estimate in one transaction per plan;
      one plan failing fails no other
- [ ] It joins the registry, both compositions, the fakes, the demo's tables and the retention
      collector at 400 days

---

### TASK-P16-006: the comment

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 5.5, OPEN-45 |
| Delivers | FEAT-096 |
| Depends on | TASK-P16-005 |
| Estimate | M |

**Acceptance criteria.**

- [ ] A pure renderer: the unpriced count first, then the monthly change, a line per resource, the
      reasons, the assumptions and the catalogue version, and a hidden marker per folder
- [ ] The code host port and the GitHub adapter write or edit a comment found by its marker, the
      comments read a page at a time, each failure typed; the fakes follow
- [ ] The collector writes or edits the comment for a plan whose commit is the pull request's head,
      leaves it alone for an older commit, and records the pull request's state

---

### TASK-P16-007: the estimate against the bill

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 5.6 |
| Delivers | FEAT-097 |
| Depends on | TASK-P16-006 |
| Estimate | M |

**Acceptance criteria.**

- [ ] A pure verdict: `WITHIN` inside 10 percent at list cost, `ABOVE`, `BELOW`, or `NOT_COMPARED`
      with its reason, and the median absolute percentage error by type
- [ ] The `estimate_comparison` collector, daily, finds a merged pull request's created resources
      in the mapped state, skips the first billed day, reads thirty, and restates as the bill does
- [ ] A migration for `estimate_comparison` with its checks and the cadence; the registry, the
      compositions, the fakes and retention follow

---

### TASK-P16-008: the routes and the screen

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 8 |
| Delivers | FEAT-095, FEAT-096, FEAT-097 |
| Depends on | TASK-P16-007 |
| Estimate | S |

**Acceptance criteria.**

- [ ] `GET /v1/estimates`, `/v1/estimates/{plan_id}` and `/v1/estimates/accuracy`, global scope,
      each with `as_of` and `collected_at`, exportable, and in the MCP facade
- [ ] The Estimates screen at `/cost/estimates`: the plans, one plan's lines with the unpriced count
      first, and the accuracy, modelled against measured; saved views widened to it
- [ ] Unit tests, and a Playwright journey

---

### TASK-P16-009: the local stack, proof and documents

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 13 |
| Delivers | The exit criteria 1 to 5, measured, and the record |
| Depends on | TASK-P16-002 to TASK-P16-008 |
| Estimate | S |

**Acceptance criteria.**

- [ ] The seeded demo carries plans in every status, comments against the fake GitHub, and
      comparisons in every verdict
- [ ] Exit criteria 1 to 5 met, each with its evidence in `tests/scripts/test_p16_exit_criteria.py`
- [ ] FEAT-095 to FEAT-097 say what was built; the register, `project_map.md` and the checkpoint
      updated, and `make check-docs` clean

---

### TASK-P16-010: a plan's arrival

| Field | Value |
| --- | --- |
| Status | Not started, waits on OPEN-44 |
| Implements | Spec section 5.1 |
| Delivers | FEAT-098, exit criterion 6 |
| Depends on | OPEN-44 answered, TASK-P16-005 |
| Estimate | S |

**Acceptance criteria.**

- [ ] The route OPEN-44 chooses records a plan as `RECEIVED` through the reduction and nothing else
- [ ] A runbook names the pipeline's step and the owner's steps
- [ ] Exit criterion 6 met with its evidence
