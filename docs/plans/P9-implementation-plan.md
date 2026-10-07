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
| B. The catalogs | 002 to 005, 012, 013 | Ports, tables, the price list for five services in every Region, the instance catalog, Savings Plans rates and spot prices | A |
| C. Targets | 006 to 009 | Compute Optimizer fixed, downsizing and upsizing to a named type, gp2 to gp3 | B |
| D. Surface | 010 | Routes and the Alternatives table | C |
| E. Proof and documents | 011 | Exit criteria measured, documents updated | All |

---

### TASK-P9-001: the hub reaches every AWS API it calls

| Field | Value |
| --- | --- |
| Status | Done 2026-10-08 |
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

- [x] An ADR records A plus C for Budgets and Support, C again for spot prices and Savings
      Plans rates in every Region, OPEN-17, why, and its monthly cost: the
      endpoint price measured from the AWS price list, the endpoints counted from the
      Terraform, and the total labelled modelled. ADR-0035: 0.011 USD per endpoint per zone
      hour in eu-west-1 and eu-west-2 and 0.010 in us-east-1, measured from offer file
      20260917190528; 21 endpoints added; about 338 USD a month in all (modelled), against
      the 290 the owner chose on
- [x] Terraform builds it, and `terraform validate` and `fmt` pass for every stack touched:
      hub, member and management on 2026-10-08, validated against the providers already
      installed, so nothing was downloaded. `endpoints.tf`, `relay.tf` and
      `modules/endpoint_vpc`
- [x] A test lists every AWS service the adapters create a client for, and holds each one
      to a path: an interface endpoint in the Region it is called in, or, for Budgets and
      Support only, one of the two functions outside the VPC.
      `tests/contract/test_network_paths.py` reads the services from the code and from the
      operations `test_response_shapes.py` declares, and four red checks failed it. Reworded
      on 2026-10-08: Invoicing, added by P10, has no interface endpoint either, measured that
      day, so it takes the same path under the owner's rule; and the two functions are one
      relay with an allow list, `finops_relay`, which the existing adapters read through
      unchanged
- [x] No NAT gateway and no default route in the hub's private subnets: every call leaves
      through an interface endpoint, the peered endpoint VPC or the S3 gateway endpoint, and
      the relay is invoked through the Lambda endpoint. Held by the same test
- [x] The comment in `infra/terraform/hub/network.tf` that calls six endpoints every
      service the tasks call is corrected, and so is `docs/04-DEPLOYMENT.md`, which names a
      Cost Explorer endpoint among the hub's own, in the hub's Region, where none can be made:
      Cost Explorer's endpoint is in us-east-1 only
- [x] Every new resource tagged `finops:module`, constraint 7: all three providers carry the
      one set of default tags, held by the same test
- [x] Spot prices and Savings Plans rates in every Region read by a function outside the VPC
      that writes rows to S3, the owner's answer to OPEN-17 on 2026-10-07, held by the same test.
      The relay allows both; reading them is TASK-P9-012 and TASK-P9-013

---

### TASK-P9-002: ports and fakes for prices and instance types

| Field | Value |
| --- | --- |
| Status | Done 2026-10-08 |
| Implements | P9 spec sections 5.3 and 5.4 |
| Delivers | `PriceCatalog` and `InstanceCatalog` ports |
| Depends on | TASK-P9-001 |
| Estimate | M |

**Acceptance criteria.**

- [x] Ports in `finops_core/ports/`, no SDK, constraint 1: `PriceCatalog` and
      `InstanceCatalog` in `catalog.py`, in a group of their own, `CATALOG_PORTS`, so the ports
      test reaches both, with the domain in `finops_core/domain/catalog.py`
- [x] Fakes in `finops_fakes/` shaped from small real extracts of the offer files and of
      `DescribeInstanceTypes`, with the planted cases' types and prices.
      `finops_fakes/catalog.py`, its term and rate codes from AWS's ElastiCache price list for
      eu-west-1, version 20260914063714, and its prices from the estate's own table so a saving
      and the bill agree. The extracts, pruned to one product each, are in
      `tests/providers/aws/extracts` with their sources; `tests/core/test_catalog.py` builds the
      domain's records from them. Reading the real list corrected the spec, section 5.3: an All
      Upfront reservation is nought an hour beside its fee, so the refusal is of a term whose
      every price is nought
- [x] A contract test both the fake and the adapter will pass,
      `tests/contract/test_catalog_contract.py`, parametrized so TASK-P9-004 and TASK-P9-005 add
      their adapters to it. Three red checks failed the tests

---

### TASK-P9-003: the catalog tables

| Field | Value |
| --- | --- |
| Status | Done 2026-10-08 |
| Implements | P9 spec section 6 |
| Delivers | Four tables and the recommendation's added columns |
| Depends on | TASK-P9-002 |
| Estimate | M |

**Acceptance criteria.**

- [x] `price_list_version`, `price`, `instance_type_spec` and `volume_type_spec`, every
      invariant in spec section 6 a constraint, with `price` holding a term's recurring price
      and upfront fee and refusing only a term that is nought in both, as corrected on
      2026-10-08. Migration 0033; a price's version is a foreign key, so no price exists
      without the publication it came from
- [x] `instance_type_spec` keyed by service as well as type, for the five services of spec
      section 14, and `spot_price` and `spot_price_daily` as OPEN-18 chose, spec section
      14.7. Added 2026-10-07
- [x] The recommendation's target columns added as nullable, constraint 12, each price id held
      by a composite foreign key to a price of the same Region and version
- [x] A test per constraint, `tests/db/test_price_catalog_constraints.py`, and
      `docs/07-DATA-MODEL.md` and `docs/09-DATA-CLASSIFICATION.md` updated in the same commit.
      Two red checks failed it. Per tenant, as every table is, rather than shared as the spec's
      table drew them, so the guard needs no new rule; the migration records why

---

### TASK-P9-004: the price list, five services, every Region, on demand and reserved

| Field | Value |
| --- | --- |
| Status | Done 2026-10-08 |
| Implements | P9 spec sections 5.2, 5.3, 7 and 14, FEAT-071 |
| Delivers | FEAT-071, on demand and reserved |
| Depends on | TASK-P9-003 |
| Estimate | L |

**Acceptance criteria.**

- [x] The adapter reads the Price List Query API for `AmazonEC2`, which holds EBS,
      `AmazonRDS`, `AmazonElastiCache`, `AmazonRedshift` and `AmazonES`, in every commercial
      Region, the Regions taken from the price list's own codes and never listed in code.
      Widened from the Regions in OPEN-06 on 2026-10-07, spec section 14
- [x] Reserved terms, one and three years, every payment option and offering class, as
      `PricingCategory` Committed with the term in `SkuPriceDetails`
- [ ] The number of price rows measured before the tables are sized, against the ten
      million spec section 14.4 models. Open, ISS-261: only the ElastiCache list for eu-west-1
      is measured, 506 products and 1,850 terms; the rest needs an account or the owner's
      permission to download an offer file
- [x] Rows filtered to the comparable price: operating system, shared tenancy, used
      capacity, no preinstalled software, with the filter tested, and Extended Support
      products named rather than read as a second price for the same type, found in the real
      ElastiCache list on 2026-10-08
- [x] A term whose every price is nought, or a missing price, refused with a typed cause,
      never stored; an All Upfront term's nought hourly rate beside its fee kept, spec section
      5.3 as corrected on 2026-10-08
- [x] The adapter added to `tests/contract/test_catalog_contract.py`, over a stub serving the
      fake's prices in GetProducts' shape. Its attribute names are held to the real EC2 EBS
      product in the API reference's sample and to the real ElastiCache list; a real EC2
      instance product is still to come, ISS-261
- [x] The `price_catalog` collector, a `collector_schedule` row with its reason and cost,
      every 8 hours, loads only the services and Regions whose version changed
- [x] Never loads a whole offer file into memory: GetProducts is read a page at a time as
      a generator, and prices are written 1,000 at a time

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
| Depends on | TASK-P9-001 and TASK-P9-003 |
| Estimate | M |

**Acceptance criteria.**

- [ ] `DescribeSpotPriceHistory` for every commercial Region, zone and product description,
      as `PricingCategory` Dynamic, with the reading's own time as `as_of` and `collected_at`
      beside it
- [ ] Read by the function outside the VPC chosen for OPEN-17, held by TASK-P9-001's test
- [ ] The latest price per pool, replaced each run, and each day's low and high kept for 90
      days, as OPEN-18 chose on 2026-10-07, spec section 14.7; every limit a database
      constraint, and the 90 days held by a test
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

- Whether the catalog gets a screen of its own, browsable like instances.vantage.sh, beside the
  Alternatives table. Which services follow EC2 and EBS, whether spot is in, OPEN-17 and
  OPEN-18 were answered on 2026-10-07.
