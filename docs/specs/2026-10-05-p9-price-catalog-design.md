# P9 Price catalog and rightsizing targets: design specification

Date: 2026-10-05
Status: Approved by the owner on 2026-10-05, and widened by the owner on 2026-10-07, section 14
Sub project: P9
Features: FEAT-071, FEAT-072, FEAT-073, FEAT-074
Depends on: P3 delivered; the network path the owner chose in section 5.1, built by TASK-P9-001, ISS-242
Supersedes: nothing

## 1. Purpose

The owner asked on 2026-10-05 for the data that lets Meter say which machine to move to
when shrinking or growing one, with current prices for EC2 instances, EBS volumes and other
services, and suggested scraping Vantage's instance site to get it.

Research the same day, section 3, found three things.

1. **Meter's rightsizing names no target and overstates the saving.** The saving is the
   instance's monthly cost times its unused fraction. For the planted m5.2xlarge at 7
   percent CPU that reports 90.9 percent of 324.12 USD a month (modelled), when one size
   down, m5.xlarge, saves 50 percent at measured list prices, and m7g.xlarge would save
   57.5 percent (modelled from measured prices).
2. **Scraping Vantage is neither necessary nor allowed.** Its site republishes AWS's own
   price list and instance data, its website terms forbid scraping, and its scraper is MIT
   licensed code that reads the same AWS sources Meter can read itself.
3. **The hub cannot reach those sources, nor most of the APIs its collectors already
   call.** Its private subnets have no default route and endpoints for six services only.
   That is ISS-242, and it gates this sub project and every collector beyond P0.

## 2. Definition of done

- Every rightsizing recommendation names a target instance type offered in the Region,
  with the current and target list prices, the price list version and its publication
  date, and the saving as their difference, labelled modelled.
- Growing an instance is recommended where measured use calls for it, and shown as an added
  monthly cost, never as a negative saving.
- A gp2 volume's move to gp3 is priced from its size and its measured IOPS and throughput.
- Compute Optimizer stays the first source of targets where it is enabled, and every ranked
  option it returns is priced and kept, not only the first.
- Every price carries its source, version, `as_of` (the publication date) and `collected_at`.
- The hub reaches every AWS API Meter calls, through the path the owner chose in 5.1.

## 3. Research, 2026-10-05

Measured means read from `pricing.us-east-1.amazonaws.com`, `instances.vantage.sh` or
GitHub on 2026-10-05. Sources are listed at the end of this section.

### 3.1 Sources compared

| Source | Authority | Terms | Freshness | Coverage | Reachable from the hub today |
| --- | --- | --- | --- | --- | --- |
| Vantage site, scraped | A copy of AWS data [V2][V5] | Website terms forbid crawling, scraping and storing a significant portion of content [V3] | Rebuilt every 8 hours [V6]; "not guaranteed to be accurate or current" [V7] | EC2 specs, on demand, reserved, Savings Plans and spot; no EBS volume prices | No, needs internet egress |
| Vantage `instances.json` or its API | Same | Code MIT [V1]; API needs a key tied to an email [V8]; data terms not stated | Same | Same; the file is 317,239,021 bytes (measured) | No |
| AWS Price List Query API | First party [A1] | Published for programmatic use | Republished when prices change, with SNS notices [A5] | Every service including EBS; no Savings Plans, no spot | No: endpoints only in us-east-1, eu-central-1 and ap-south-1 [A1], PrivateLink only there [A6] |
| AWS Price List bulk files | First party [A2][A3] | Same | Same | Every service, Savings Plans and reserved; no spot | No: public host |
| EC2 `DescribeInstanceTypes` and `DescribeInstanceTypeOfferings` | First party [A9] | AWS | Live | Specs per Region, no prices, no burstable baseline [A10][A11] | No `ec2` endpoint |
| Compute Optimizer | First party [A12] | AWS | 14 day lookback, about 3 months with paid metrics [A13] | Ranked targets with a performance risk and savings | No endpoint; the adapter calls us-east-1 only |
| The bill, CUR 2.0 as FOCUS | The bill | AWS | Up to three times a day | What the estate actually pays | No `athena` endpoint |

### 3.2 What AWS publishes, measured

| Item | Value |
| --- | --- |
| Offer index | 272 offers, published 2026-10-05T00:07:45Z, readable without credentials [A2] |
| EBS | Inside the `AmazonEC2` offer, as product families Storage, Provisioned Throughput and System Operation |
| Region file sizes, bytes | eu-west-1 JSON 441,439,512, CSV 281,481,379; eu-west-2 JSON 317,433,336, CSV 212,268,450; the global EC2 JSON 9,084,827,898 |
| eu-west-2 Linux on demand, USD an hour | m5.2xlarge 0.444, m5.xlarge 0.222, m7i.xlarge 0.2331, m8g.xlarge 0.2076, m7g.xlarge 0.1887, t3.medium 0.0472, t3.small 0.0236 |
| eu-west-2 EBS, USD | gp2 0.116 and gp3 0.0928 per GB month; gp3 throughput 0.0464 per MiBps month |
| gp2 and gp3 | gp3 includes 3,000 IOPS and 125 MiB/s, to 80,000 IOPS and 2,000 MiB/s at extra cost; gp2 gives 3 IOPS per GiB, 100 to 16,000, and bursts to 3,000 under 1 TiB [A15] |
| Burstable baselines | Only in the EC2 guide's table, for example t3.medium earns 24 credits an hour and has a 20 percent baseline per vCPU [A11]; the API has no baseline field [A10] |
| Price change notices | `price-list-api` SNS topics in us-east-1 [A5] |

### 3.3 What Meter has today

| Area | Finding | Where |
| --- | --- | --- |
| Catalog | None in any production package | |
| CPU rightsizing | Saving is monthly cost times the unused fraction; no target named | `finops_query/waste.py:153-160` |
| Burstable | A flat credit floor of 20, not relative to the type | `finops_query/waste.py:52`, `:136` |
| Fargate | A hard coded size matrix and `snap_up`, the pattern to copy | `finops_query/containers.py:224-282` |
| Candidate | `monthly_cost` only, no instance type, operating system or tenancy | `finops_ingest/collectors/waste_compute.py:68-79` |
| Metrics | CPU average and agent memory maximum; no network or EBS series | `finops_ingest/collectors/waste_compute.py:179-206` |
| Compute Optimizer | One call to us-east-1 with no member account and no `nextToken`, keeping the first option as text | `finops_providers/aws/recommendations.py:51`, `:175-220` |
| Bill | Has `sku_id`, `list_cost` and `contracted_cost`; no `SkuPriceId`, `ListUnitPrice` or `PricingUnit` | `finops_core/domain/cost.py:196-203` |
| Fakes | Planted cases: an m5.2xlarge at 7 percent, a 1000 GiB gp2 volume, a c6i.2xlarge above 90 percent | `finops_fakes/planted.py:113`, `:151`, `:238` |
| A waiting consumer | FEAT-047 needs "the instance catalogue with on demand and Spot pricing" | `docs/features/FEAT-047-node-fleet-optimisation.md:22` |
| Network | Private subnets, no default route; endpoints for `sts`, `sqs`, `secretsmanager`, `logs`, `ecr.api`, `ecr.dkr` and the S3 gateway only | `infra/terraform/hub/network.tf:28-35`, `:94-99` |

### 3.4 Sources

- V1 https://github.com/vantage-sh/ec2instances.info
- V2 https://github.com/vantage-sh/ec2instances.info/blob/main/README.md
- V3 https://www.vantage.sh/legal/website-terms-of-use
- V5 https://github.com/vantage-sh/ec2instances.info/tree/main/scraper
- V6 https://github.com/vantage-sh/ec2instances.info/blob/main/.github/workflows/production-release.yml
- V7 https://handbook.vantage.sh/tools/instances/
- V8 https://www.vantage.sh/blog/instances-api-sdk
- A1 https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/price-changes.html
- A2 https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/using-the-aws-price-list-bulk-api-fetching-price-list-files-manually.html
- A3 https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/using-the-aws-price-list-bulk-api.html
- A5 https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/price-notification.html
- A6 https://aws.amazon.com/about-aws/whats-new/2025/02/aws-price-list-api-privatelink
- A8 https://docs.aws.amazon.com/vpc/latest/privatelink/aws-services-cross-region-privatelink-support.html
- A9 https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstanceTypes.html
- A10 https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_InstanceTypeInfo.html
- A11 https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-credits-baseline-concepts.html
- A12 https://docs.aws.amazon.com/compute-optimizer/latest/APIReference/API_GetEC2InstanceRecommendations.html
- A13 https://aws.amazon.com/compute-optimizer/pricing/
- A15 https://docs.aws.amazon.com/ebs/latest/userguide/general-purpose.html
- F1 https://github.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS_Spec/tree/v1.1/specification/columns

## 4. Out of scope

- **Scraping any website, and any third party price data.** Every price comes from AWS.
- **Applying a change.** Constraint 6. A recommendation stays advice.
- **Spot prices, Savings Plans and reserved rate cards, and services beyond EC2 and EBS**
  were out of scope until 2026-10-07, when the owner widened the catalog to all of them,
  section 14. A rightsizing saving is still the difference between two list on demand
  prices, scaled to what the estate pays, 5.6.

## 5. The decisions this sub project rests on

### 5.1 The hub reaches every AWS API it calls, by a path the owner chooses

This is a prerequisite and an ADR. Today a deployed hub would reach six services; the
collectors call about fifteen more. Cost Explorer, Organizations, Budgets, Support, IAM and
Cost Optimization Hub answer only in us-east-1, the Price List Query API only in us-east-1,
eu-central-1 and ap-south-1 (section 3.1), and calls into eu-west-2 need that Region's
endpoints. Cross Region PrivateLink does not cover them [A8]. Budgets and Support have no
interface endpoint at all (measured 2026-10-05 against the AWS PrivateLink service list,
https://docs.aws.amazon.com/vpc/latest/privatelink/aws-services-privatelink-support.html),
so option A cannot reach those two on its own, and the ADR prices B against A plus a
contained path for those two.

| Option | What | Fits the design | Cost | Moving parts |
| --- | --- | --- | --- | --- |
| A. Endpoints everywhere | An interface endpoint in each Region used for every regional service called, plus a small endpoint VPC in us-east-1 peered to the hub for the global ones | Keeps "no default route", the hub's design | About 14.7 USD a month per endpoint across two zones (modelled, `docs/04-DEPLOYMENT.md`), times about twenty, plus peering | Most: endpoints, peering and private DNS per Region |
| B. A NAT with an allow list | One NAT gateway per zone, egress limited to AWS service domains by a DNS or network firewall | Opens an egress path ADR-0028 would have to be reopened for | To be priced in the ADR | Fewest |
| C. Collectors outside the VPC | Functions with no VPC that call the APIs and write rows to S3 | Splits the ingest runtime | Low | Two runtimes, two deploy paths |

The recommendation is A, because the hub was designed to have no route out and every
other control assumes it. B is the fallback if A's cost or complexity is refused. The owner
decides; the ADR records the choice and its price.

**The owner's decision, 2026-10-05: A, plus C for two.** An interface endpoint for every
service that has one: the endpoint VPC in us-east-1 for the services that answer only there,
and endpoints in each Region called for the rest. Budgets and Support have no interface
endpoint, so those two alone take C: two small functions outside the VPC that call them and
write rows to S3, which the hub reads through the S3 gateway endpoint it already has. The hub
keeps no route out, which ADR-0028 relies on, and B is not built. About 20 endpoints at about
14.7 USD a month each is roughly 290 USD a month (modelled); the ADR that TASK-P9-001 writes
measures it. OPEN-16 is answered.

### 5.2 Prices come from AWS, never from a third party

The Price List Query API, filtered to the two Regions in OPEN-06, for on demand EC2 and
EBS. Vantage's MIT scraper is a reference for SKU filtering rules, never a data source.
Widened on 2026-10-07 to every commercial Region, five services and four price types,
section 14.

### 5.3 The catalog is FOCUS shaped and versioned

Constraint 2. Every price row carries `SkuId`, `SkuPriceId` (the AWS RateCode),
`ListUnitPrice`, `PricingUnit`, `PricingCategory` (Standard for on demand), the billing
currency and `SkuPriceDetails`: operating system, tenancy, capacity status, preinstalled
software and licence. A version is the offer file's publication, and `as_of` is its
`publicationDate`. A zero or missing price is refused with a typed cause, never stored.

### 5.4 Capabilities from EC2's own description of itself

`DescribeInstanceTypes` and `DescribeInstanceTypeOfferings`, per Region: vCPUs, memory,
architectures, generation, network baseline and peak, EBS baseline and maximum, GPUs, and
whether the type is offered. Burstable baselines come from the EC2 guide's table, kept as
data with its source, and a test fails when the API lists a burstable type the table lacks.

### 5.5 Targets: Compute Optimizer first, Meter's rule where it is blind

ADR-0006 puts AWS's own recommendation first. The Compute Optimizer adapter is fixed to
call each Region, pass one member account per request, follow `nextToken`, ask for Graviton
through its architecture preference, and keep every ranked option, each priced from the
catalog. Where Compute Optimizer is not enabled or has no answer, Meter's own rule:

- **Candidates:** the same family one or two sizes away, the newer generation, Graviton and
  AMD variants, every one offered in the Region.
- **Fit:** CPU p99 times 1.30 against the target's vCPUs; memory peak times 1.15, or 1.25
  after an out of memory kill; network and EBS p99 against the target's baseline, never its
  burst. Across a generation or an architecture, the recommendation says vCPUs are not
  equivalent and Graviton needs arm64 builds.
- **Snap to a real type:** the cheapest candidate that fits, as P6 snaps Fargate sizes.
- **No agent, no memory figure:** only one step down within the family, and the rationale
  says why.

### 5.6 A saving is modelled from list prices, and scaled to what is paid

The saving is the current type's list price minus the target's, for the hours the instance
runs. List is not what an estate pays, so the saving is also shown scaled by the ratio of
effective to list cost for that instance in the bill, and both figures are labelled
modelled, with the price version beside them.

### 5.7 Growing is a cost, never a negative saving

CPU or memory p95 above 90 percent, or bandwidth at its baseline, recommends the next size
or a family with more memory per vCPU. It is a recommendation of its own kind, Upsize, with
an added monthly cost, so no total of savings can be reduced by it.

### 5.8 gp2 to gp3

The IOPS a volume needs is the larger of its gp2 baseline and its measured p99. The gp3
cost is storage, plus IOPS above 3,000, plus throughput above 125 MiB/s. For example, a
1,000 GiB volume needing 250 MiB/s costs 116.00 USD a month on gp2 and 98.60 on gp3,
92.80 plus 5.80, a saving of 17.40 (modelled from measured eu-west-2 prices).

## 6. Data model

Every invariant a constraint, constraint 11, and every migration additive, constraint 12.

| Table | Holds | Key constraints |
| --- | --- | --- |
| `price_list_version` | provider, service code, Region, version, `as_of` (publication date), `collected_at`, row count | unique per service, Region and version |
| `price` | provider, service name and category, Region, SKU, `sku_price_id`, `sku_meter`, `pricing_unit`, `list_unit_price`, currency, `pricing_category`, `sku_price_details`, effective date, version, `as_of`, `collected_at` | `list_unit_price > 0`; `collected_at >= as_of`; unique per Region, `sku_price_id` and version |
| `instance_type_spec` | Region, instance type, family, generation, current generation, architectures, burstable, baseline CPU and maximum credits with their source, vCPUs, memory, network baseline and peak, EBS baseline and maximum, GPU count, offered, `as_of`, `collected_at` | positive vCPUs and memory; a burstable type has a baseline |
| `volume_type_spec` | volume type, included IOPS and throughput, maxima, IOPS per GiB, source, `as_of` | |
| `recommendation`, added | nullable current `sku_price_id`, target instance type, target `sku_price_id`, price version | a target names a price from the same version |

## 7. Collectors and cadence

Cadence is data, constraint 9 and ADR-0012: each is a `collector_schedule` row with its
reason and cost.

| Collector | Scope | Cadence | Reason |
| --- | --- | --- | --- |
| `price_catalog` | organization | daily | Offer files change irregularly; each run compares the stored version and stops when it is unchanged |
| `instance_catalog` | per Region | daily | New instance types appear between releases |

Files are streamed as CSV with the standard library, filtered to the two Regions, and the
441 MB JSON is never loaded.

The owner set every catalog collector to run every 8 hours on 2026-10-07, section 14. Each
run still compares what AWS has published with what is stored and stops when nothing changed.

## 8. Interface

- `GET /catalog/instance-types`, filtered by family, architecture, vCPUs and memory.
- `GET /catalog/prices`, filtered by service, Region and SKU, with the version and `as_of`.
- Recommendations gain the target type, both prices, the version and the scaled saving.
- On the recommendation's screen, an Alternatives table: type, vCPUs, memory, network
  baseline, price per hour and month, and saving, the chosen target first.

## 9. Testing

- Parsers against small real extracts of the offer files; a zero price refused; the SKU
  filters for Linux, shared tenancy, used capacity and no preinstalled software.
- An unchanged version does no work.
- The Compute Optimizer adapter across Regions, accounts and pages, keeping every option.
- The planted cases: the m5.2xlarge at 7 percent names a target and saves its price
  difference; the c6i.2xlarge above 90 percent is an Upsize with an added cost; the 1000 GiB
  gp2 volume is priced as gp3.
- No total of savings ever falls because of an Upsize.
- A burstable type the table lacks fails a test.
- Every AWS service an adapter calls has a path from the hub, by the option chosen in 5.1.

## 10. Risks

- **The network.** Nothing here reaches AWS until the path chosen in 5.1 is built, TASK-P9-001.
- **List is not what is paid.** Private pricing and commitment discounts make list savings
  overstate; 5.6 scales them and labels both.
- **SKU matching.** One type has many price rows. The filters in section 9 decide which is
  the comparable one, and the London file holds zero priced rows for allocated reservations
  (measured), which are refused.
- **Comparability.** vCPUs differ by generation and architecture; the recommendation says so.
- **Gaps.** The Price List has no spot, and burstable baselines come from documentation.

## 11. Open questions

- OPEN-16, the network path in 5.1. ANSWERED 2026-10-05: A, plus C for Budgets and Support.
- Which services after EC2 and EBS. ANSWERED 2026-10-07: RDS, ElastiCache, Redshift and
  OpenSearch, section 14.
- OPEN-17, how the hub reads spot prices and Savings Plans rates in every Region, 14.5.
- OPEN-18, how much spot price history is kept, 14.5.

## 12. Features delivered

FEAT-071 price catalog for five services, every Region and four price types; FEAT-072
instance capability catalog for the same five services; FEAT-073 rightsizing to a named,
priced target, down and up; FEAT-074 gp2 to gp3 priced.

## 13. Exit criteria

1. The hub reaches every AWS API an adapter calls, by the chosen path, tested.
2. Every rightsizing recommendation names an offered target with both prices and the version.
3. The three planted cases come out as section 9 says.
4. Every price row carries its version, `as_of` and `collected_at`, and no zero price exists.
5. The catalog holds every commercial Region, the five services and the four price types of
   section 14, and a run that finds nothing newly published does no work.

## 14. Scope widened, 2026-10-07

### 14.1 The ask

The owner asked on 2026-10-07 for the data instances.vantage.sh shows, held in Meter's own
database and kept current by polling AWS for what it publishes. Scraping that site stays out of
scope, section 4: every figure on it is AWS's own, so Meter reads AWS directly.

### 14.2 The owner's decisions, 2026-10-07

| Question | Decision |
| --- | --- |
| Regions | Every commercial Region, taken from the price list's own Region codes and never listed in code |
| Price types | On demand; reserved, one and three years, every payment option and offering class; Savings Plans rates; spot |
| Services | EC2 with EBS, RDS, ElastiCache, Redshift and OpenSearch |
| Polling | Every 8 hours, each run loading only what AWS has published since the last |

### 14.3 Where each part comes from

| Part | Source | Path from the hub |
| --- | --- | --- |
| On demand and reserved prices, five services | The Price List Query API by service code, `AmazonEC2`, `AmazonRDS`, `AmazonElastiCache`, `AmazonRedshift` and `AmazonES`, and by Region code. Reserved rates are the same products' reserved terms | The endpoint in us-east-1 already in option A |
| Specs of RDS, ElastiCache, Redshift and OpenSearch instances | The same products' attributes: vCPUs, memory, network and storage | The same endpoint |
| Specs of EC2 instance types | `DescribeInstanceTypes` in the hub's own Region, with the Regions a type is sold in taken from the price list. A test compares two Regions' descriptions so the assumption that a type is described alike everywhere is held, not trusted | The hub's own `ec2` endpoint, already in option A |
| Savings Plans rates | The Savings Plans price list, per Region | OPEN-17 |
| Spot prices | `DescribeSpotPriceHistory`, per Region and zone | OPEN-17 |

Prices for every Region come through the one endpoint in us-east-1, so spot prices and Savings
Plans rates are the only reads that need a path into each Region.

### 14.4 Volume and polling

Every 8 hours each catalog collector compares the version AWS has published, per service and
Region, with the stored one, and loads only those that changed, so a run that finds nothing is
a few small calls. Prices are read through the Query API by service and Region, so the global
EC2 file, 9,084,827,898 bytes (measured), is never downloaded. The whole catalog is on the order
of ten million price rows (modelled from the instance types, Regions, operating systems and
reserved terms each service sells), and TASK-P9-004 measures it before the tables are sized. A
Region the account has not opted into answers spot calls with NotOptedIn, a typed failure that
never becomes a price of nought, constraint 5.

### 14.5 Open, for the owner

- **OPEN-17, the path for spot prices and Savings Plans rates in every Region.** Recommended: C,
  a small function outside the VPC that calls each Region and writes rows to S3, the pattern
  approved for Budgets and Support on 2026-10-05, at a few USD a month (modelled). The
  alternative is A, an interface endpoint for each in every Region: about 30 Regions at about
  14.7 USD a month an endpoint, roughly 440 USD a month for spot alone (modelled), on top of
  the 290 USD a month already approved.
- **OPEN-18, how much spot price history is kept.** Recommended: the latest price per pool,
  replaced each run, plus each day's low and high kept for 90 days. The alternatives are every
  8 hourly reading kept, which grows without limit, or the latest only, as the Vantage site
  shows.

### 14.6 What changes in the plan

TASK-P9-004 loads the five services in every Region, on demand and reserved. TASK-P9-005 covers
the five services' specs. Two tasks are added: TASK-P9-012 for Savings Plans rates once OPEN-17
is answered, and TASK-P9-013 for spot prices once OPEN-17 and OPEN-18 are. Every catalog
collector runs every 8 hours.

