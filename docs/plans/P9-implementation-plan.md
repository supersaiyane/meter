# P9 Price catalog and rightsizing targets: implementation plan

Date: 2026-10-05
Status: Approved by the owner on 2026-10-05, with its spec, and widened by the owner on 2026-10-07, spec section 14
Spec: `docs/specs/2026-10-05-p9-price-catalog-design.md`
Depends on: P3 delivered; the network path the owner chose on 2026-10-05, OPEN-16, which TASK-P9-001 builds
Tasks: 13

Meter tells an engineer an instance is too big and does not say what to move to, and the
saving it quotes assumes the unused part of an instance can be returned on its own. This
sub project gives every recommendation a real target and a real price, from AWS's own
price list and its own description of every instance type. It starts by giving the hub a
way to reach AWS at all, because today it cannot reach most of what it already calls.

## How to work this plan

Same contract as P0 through P8. One task, one commit.

**Five rules specific to P9.**

1. **Nothing reaches AWS until the network path is built.** TASK-P9-001 is the gate. It
   builds the path the owner chose on 2026-10-05 in spec section 5.1, interface endpoints
   plus two functions outside the VPC for Budgets and Support, and records it in an ADR.
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
| A. A way out | 001 | The hub reaches every AWS API it calls | This plan approved and OPEN-16 answered, both 2026-10-05 |
| B. The catalogs | 002 to 005, 012, 013 | Ports, tables, the price list for five services in every Region, the instance catalog, Savings Plans rates and spot prices | A; 013 also waits on OPEN-18 |
| C. Targets | 006 to 009 | Compute Optimizer fixed, downsizing and upsizing to a named type, gp2 to gp3 | B |
| D. Surface | 010 | Routes and the Alternatives table | C |
| E. Proof and documents | 011 | Exit criteria measured, documents updated | All |

---

### TASK-P9-001: the hub reaches every AWS API it calls

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P9 spec section 5.1 |
| Delivers | ISS-242 closed |
| Depends on | This plan approved and OPEN-16 answered, both 2026-10-05 |
| Estimate | L |

**Goal.** The path the owner chose on 2026-10-05, spec section 5.1, built in Terraform,
recorded in an ADR with its price, and held by a test. Option A for every service that has
an interface endpoint: an endpoint VPC in us-east-1, peered to the hub, for the services that
answer only there, and endpoints in each Region called for the rest. Option C for the two
that have none, Budgets and Support: two small functions outside the VPC that call them and
write rows to S3. The hub keeps no route out, which ADR-0028 relies on.

**Acceptance criteria.**

- [ ] An ADR records A plus C for Budgets and Support, C again for spot prices and Savings
      Plans rates in every Region, OPEN-17, why, and its monthly cost: the
      endpoint price measured from the AWS price list, the endpoints counted from the
      Terraform, and the total labelled modelled. The estimate the owner chose on was about
      20 endpoints at about 14.7 USD a month each, roughly 290 USD a month (modelled)
- [ ] Terraform builds it, and `terraform validate` and `fmt` pass for every stack touched
- [ ] A test lists every AWS service the adapters create a client for, and holds each one
      to a path: an interface endpoint in the Region it is called in, or, for Budgets and
      Support only, one of the two functions outside the VPC
- [ ] No NAT gateway and no default route in the hub's private subnets: every call leaves
      through an interface endpoint, the peered endpoint VPC or the S3 gateway endpoint
- [ ] The comment in `infra/terraform/hub/network.tf` that calls six endpoints every
      service the tasks call is corrected, and so is `docs/04-DEPLOYMENT.md`, which names a
      Cost Explorer endpoint among the hub's own, in the hub's Region, where none can be made:
      Cost Explorer's endpoint is in us-east-1 only
- [ ] Every new resource tagged `finops:module`, constraint 7
- [ ] Spot prices and Savings Plans rates in every Region read by a function outside the VPC
      that writes rows to S3, the owner's answer to OPEN-17 on 2026-10-07, held by the same test

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
- [ ] `instance_type_spec` keyed by service as well as type, for the five services of spec
      section 14, and the spot tables as OPEN-18 decides. Added 2026-10-07
- [ ] The recommendation's target columns added as nullable, constraint 12
- [ ] A test per constraint, and `docs/07-DATA-MODEL.md` and
      `docs/09-DATA-CLASSIFICATION.md` updated in the same commit

---

### TASK-P9-004: the price list, five services, every Region, on demand and reserved

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P9 spec sections 5.2, 5.3, 7 and 14, FEAT-071 |
| Delivers | FEAT-071, on demand and reserved |
| Depends on | TASK-P9-003 |
| Estimate | L |

**Acceptance criteria.**

- [ ] The adapter reads the Price List Query API for `AmazonEC2`, which holds EBS,
      `AmazonRDS`, `AmazonElastiCache`, `AmazonRedshift` and `AmazonES`, in every commercial
      Region, the Regions taken from the price list's own codes and never listed in code.
      Widened from the Regions in OPEN-06 on 2026-10-07, spec section 14
- [ ] Reserved terms, one and three years, every payment option and offering class, as
      `PricingCategory` Committed with the term in `SkuPriceDetails`
- [ ] The number of price rows measured before the tables are sized, against the ten
      million spec section 14.4 models
- [ ] Rows filtered to the comparable price: operating system, shared tenancy, used
      capacity, no preinstalled software, with the filter tested
- [ ] A zero or missing price refused with a typed cause, never stored
- [ ] The `price_catalog` collector, a `collector_schedule` row with its reason and cost,
      every 8 hours, loads only the services and Regions whose version changed
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

- [ ] EC2 types from `DescribeInstanceTypes` in the hub's own Region, paged, with the
      Regions each is sold in taken from the price list, and a test that compares two
      Regions' descriptions of the same types. Changed 2026-10-07, spec section 14.3
- [ ] RDS, ElastiCache, Redshift and OpenSearch instance specs from their price list
      products' attributes, into the same table keyed by service
- [ ] Burstable baselines and maximum credits from the EC2 guide's table, kept as data with
      their source, and a test that fails when a burstable type is missing from it
- [ ] The `instance_catalog` collector with its schedule row, every 8 hours; one Region or
      service failing does not fail the run

---

### TASK-P9-012: Savings Plans rates, every Region

Added 2026-10-07 at the owner's request, spec section 14.

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P9 spec section 14, FEAT-071 |
| Delivers | Savings Plans rates in the price catalog |
| Depends on | TASK-P9-001 and TASK-P9-004 |
| Estimate | M |

**Acceptance criteria.**

- [ ] Savings Plans rates from AWS's Savings Plans price list for every commercial Region, as
      `price` rows with `PricingCategory` Committed and the plan's term in `SkuPriceDetails`
- [ ] Read by the function outside the VPC chosen for OPEN-17, held by TASK-P9-001's test
- [ ] Polled every 8 hours with the other catalog collectors, loading only what changed

---

### TASK-P9-013: spot prices, every Region and zone

Added 2026-10-07 at the owner's request, spec section 14.

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P9 spec section 14, FEAT-071 |
| Delivers | Spot prices in the price catalog |
| Depends on | TASK-P9-001, TASK-P9-003, and OPEN-18 answered |
| Estimate | M |

**Acceptance criteria.**

- [ ] `DescribeSpotPriceHistory` for every commercial Region, zone and product description,
      as `PricingCategory` Dynamic, with the reading's own time as `as_of` and `collected_at`
      beside it
- [ ] Read by the function outside the VPC chosen for OPEN-17, held by TASK-P9-001's test
- [ ] Kept as OPEN-18 decides, every limit a database constraint
- [ ] Polled every 8 hours; a Region that refuses, or that the account has not opted into, is
      a typed failure such as NotOptedIn and never a price of nought, constraint 5

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

- [ ] `GET /catalog/instance-types` and `GET /catalog/prices`, with version and `as_of`,
      filtered by service, Region and pricing category as well. Widened 2026-10-07
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
| Depends on | TASK-P9-001 to TASK-P9-010, TASK-P9-012 and TASK-P9-013 |
| Estimate | S |

**Acceptance criteria.**

- [ ] Every exit criterion in spec section 13 met, each with its evidence
- [ ] FEAT-071 to FEAT-074 carry as built sections; the register, `project_map.md` and the
      checkpoint updated, and `make check-docs` clean

---

## What this plan does not answer

- OPEN-18, how much spot price history is kept, spec section 14.5.
- Whether the catalog gets a screen of its own, browsable like instances.vantage.sh, beside the
  Alternatives table. Which services follow EC2 and EBS, whether spot is in, and OPEN-17 were
  answered on 2026-10-07.
