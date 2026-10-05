# P9 Price catalog and rightsizing targets: implementation plan

Date: 2026-10-05
Status: Provisional, pending approval of `docs/specs/2026-10-05-p9-price-catalog-design.md`
Spec: `docs/specs/2026-10-05-p9-price-catalog-design.md`
Depends on: P3 delivered; the owner's choice of network path, OPEN-16
Tasks: 11

Meter tells an engineer an instance is too big and does not say what to move to, and the
saving it quotes assumes the unused part of an instance can be returned on its own. This
sub project gives every recommendation a real target and a real price, from AWS's own
price list and its own description of every instance type. It starts by giving the hub a
way to reach AWS at all, because today it cannot reach most of what it already calls.

## How to work this plan

Same contract as P0 through P8. One task, one commit.

**Five rules specific to P9.**

1. **Nothing reaches AWS until the network decision lands.** TASK-P9-001 is the gate, and
   it is the owner's choice of option in spec section 5.1, recorded in an ADR.
2. **Every price comes from AWS.** No website is scraped and no third party data is read.
   Vantage's MIT code may be read as a reference for SKU filtering, nothing more.
3. **A price is versioned and dated.** Every row carries the offer file's version, its
   publication date as `as_of`, and `collected_at`. A zero or missing price is refused.
4. **A saving is a difference between two real prices.** Never a fraction of a bill. Both
   the list difference and the difference scaled to what the estate pays are shown, labelled
   modelled, with the version beside them.
5. **Growing is a cost.** An Upsize is its own kind of recommendation with an added cost,
   and no total of savings may fall because of one.

## Wave overview

| Wave | Tasks | Delivers | Can start when |
| --- | --- | --- | --- |
| A. A way out | 001 | The hub reaches every AWS API it calls | The owner chooses an option, OPEN-16 |
| B. The catalogs | 002 to 005 | Ports, tables, the price list and the instance catalog | A |
| C. Targets | 006 to 009 | Compute Optimizer fixed, downsizing and upsizing to a named type, gp2 to gp3 | B |
| D. Surface | 010 | Routes and the Alternatives table | C |
| E. Proof and documents | 011 | Exit criteria measured, documents updated | All |

---

### TASK-P9-001: the hub reaches every AWS API it calls

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P9 spec section 5.1 |
| Delivers | ISS-236 closed |
| Depends on | The owner's choice, OPEN-16 |
| Estimate | L |

**Goal.** The option the owner chose, built in Terraform, recorded in an ADR with its price,
and held by a test.

**Acceptance criteria.**

- [ ] An ADR records the option chosen from spec section 5.1, why, and its monthly cost,
      modelled
- [ ] Terraform builds it, and `terraform validate` and `fmt` pass for every stack touched
- [ ] A test lists every AWS service the adapters create a client for, and holds each one
      to a path from the hub by the chosen option
- [ ] The comment in `infra/terraform/hub/network.tf` that calls six endpoints every
      service the tasks call is corrected, and so is `docs/04-DEPLOYMENT.md`, which names a
      Cost Explorer endpoint that does not exist
- [ ] Every new resource tagged `finops:module`, constraint 7

---

### TASK-P9-002: ports and fakes for prices and instance types

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P9 spec sections 5.3 and 5.4 |
| Delivers | `PriceCatalog` and `InstanceCatalog` ports |
| Depends on | TASK-P9-001 |
| Estimate | M |

**Acceptance criteria.**

- [ ] Ports in `finops_core/ports/`, no SDK, constraint 1
- [ ] Fakes in `finops_fakes/` shaped from small real extracts of the offer files and of
      `DescribeInstanceTypes`, with the planted cases' types and prices
- [ ] A contract test both the fake and the adapter will pass

---

### TASK-P9-003: the catalog tables

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P9 spec section 6 |
| Delivers | Four tables and the recommendation's added columns |
| Depends on | TASK-P9-002 |
| Estimate | M |

**Acceptance criteria.**

- [ ] `price_list_version`, `price`, `instance_type_spec` and `volume_type_spec`, every
      invariant in spec section 6 a constraint
- [ ] The recommendation's target columns added as nullable, constraint 12
- [ ] A test per constraint, and `docs/07-DATA-MODEL.md` and
      `docs/09-DATA-CLASSIFICATION.md` updated in the same commit

---

### TASK-P9-004: the price list, EC2 and EBS, two Regions

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P9 spec sections 5.2, 5.3 and 7, FEAT-071 |
| Delivers | FEAT-071 |
| Depends on | TASK-P9-003 |
| Estimate | L |

**Acceptance criteria.**

- [ ] The adapter reads the Price List Query API, filtered to the Regions in OPEN-06, for
      the `AmazonEC2` offer, which holds EBS
- [ ] Rows filtered to the comparable price: operating system, shared tenancy, used
      capacity, no preinstalled software, with the filter tested
- [ ] A zero or missing price refused with a typed cause, never stored
- [ ] The `price_catalog` collector, a `collector_schedule` row with its reason and cost,
      stops when the stored version is current
- [ ] Never loads a whole offer file into memory

---

### TASK-P9-005: the instance capability catalog

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P9 spec section 5.4, FEAT-072 |
| Delivers | FEAT-072 |
| Depends on | TASK-P9-003 |
| Estimate | M |

**Acceptance criteria.**

- [ ] `DescribeInstanceTypes` and `DescribeInstanceTypeOfferings` per Region, paged, into
      `instance_type_spec`
- [ ] Burstable baselines and maximum credits from the EC2 guide's table, kept as data with
      their source, and a test that fails when a burstable type is missing from it
- [ ] The `instance_catalog` collector with its schedule row; one Region failing does not
      fail the run

---

### TASK-P9-006: Compute Optimizer, every Region, every account, every option

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P9 spec section 5.5 |
| Delivers | Compute Optimizer targets kept and priced |
| Depends on | TASK-P9-004, TASK-P9-005 |
| Estimate | M |

**Acceptance criteria.**

- [ ] The adapter calls each Region, one member account per request, follows `nextToken`,
      and asks for Graviton through its architecture preference
- [ ] Every ranked option kept, each priced from the catalog, with its performance risk
- [ ] An option whose type has no price in the catalog is kept and says so, never priced
      at zero

---

### TASK-P9-007: downsizing to a named, priced target

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P9 spec sections 5.5 and 5.6, FEAT-073 |
| Delivers | FEAT-073, with TASK-P9-008 |
| Depends on | TASK-P9-006 |
| Estimate | L |

**Acceptance criteria.**

- [ ] Candidates, fit and snapping as in spec section 5.5, where Compute Optimizer has no
      answer
- [ ] The metrics batch gains network and EBS series, so the fit can check them
- [ ] The saving is the price difference for the hours run, shown at list and scaled to
      the bill's effective to list ratio, both modelled, with the price version
- [ ] Across a generation or an architecture, the rationale says vCPUs are not equivalent
- [ ] The planted m5.2xlarge at 7 percent names a target and saves its price difference,
      no longer 90.9 percent of its cost

---

### TASK-P9-008: upsizing, as an added cost

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P9 spec section 5.7, FEAT-073 |
| Delivers | FEAT-073, with TASK-P9-007 |
| Depends on | TASK-P9-007 |
| Estimate | M |

**Acceptance criteria.**

- [ ] CPU or memory p95 above 90 percent, or bandwidth at its baseline, recommends the next
      size or a family with more memory per vCPU
- [ ] An Upsize is its own kind with an added monthly cost, migration included
- [ ] No total of savings falls because of an Upsize, tested
- [ ] The planted c6i.2xlarge above 90 percent comes out as an Upsize

---

### TASK-P9-009: gp2 to gp3, priced

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P9 spec section 5.8, FEAT-074 |
| Delivers | FEAT-074 |
| Depends on | TASK-P9-004 |
| Estimate | S |

**Acceptance criteria.**

- [ ] Needed IOPS is the larger of the gp2 baseline and the measured p99; gp3 cost is
      storage plus IOPS above 3,000 plus throughput above 125 MiB/s
- [ ] The planted 1000 GiB gp2 volume priced as gp3, with the working shown

---

### TASK-P9-010: routes and the Alternatives table

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P9 spec section 8 |
| Delivers | The catalog routes and the Alternatives table |
| Depends on | TASK-P9-007, TASK-P9-008, TASK-P9-009 |
| Estimate | M |

**Acceptance criteria.**

- [ ] `GET /catalog/instance-types` and `GET /catalog/prices`, with version and `as_of`
- [ ] Recommendations return the target, both prices, the version and the scaled saving
- [ ] The recommendation's screen shows an Alternatives table, the chosen target first,
      in P8's design system if it has landed
- [ ] Exportable through P8's export responder where it exists

---

### TASK-P9-011: proof and documents

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P9 spec sections 9 and 13 |
| Delivers | The exit criteria, measured, and the record |
| Depends on | TASK-P9-001 to TASK-P9-010 |
| Estimate | S |

**Acceptance criteria.**

- [ ] Every exit criterion in spec section 13 met, each with its evidence
- [ ] FEAT-071 to FEAT-074 carry as built sections; the register, `project_map.md` and the
      checkpoint updated, and `make check-docs` clean

---

## What this plan does not answer

- OPEN-16, which network option the hub takes. The plan cannot start without it.
- Which services after EC2 and EBS go into the catalog.
- Spot prices, which wait for FEAT-047.
