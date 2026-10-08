# FEAT-071: Price catalog from AWS for EC2, EBS, RDS, ElastiCache, Redshift and OpenSearch, every Region and price type, versioned and FOCUS shaped

| Field | Value |
| --- | --- |
| Sub project | P9 |
| Status | In build |
| Specification | [P9 spec](../specs/2026-10-05-p9-price-catalog-design.md), sections 5.2, 5.3, 7 and 14 |
| Tasks | TASK-P9-004, on demand and reserved, TASK-P9-012, Savings Plans rates, and TASK-P9-013, spot, done 2026-10-08. TASK-P9-010 serves it as `GET /catalog/prices`, done 2026-10-08 |
| Refresh cadence | Every 8 hours, the catalog collectors, each loading only what AWS has published since the last run |

## What it does

Holds AWS's own list prices in Meter's database: on demand, and reserved for one and three years
in every payment option and offering class, for five services, `AmazonEC2` (which holds EBS),
`AmazonRDS`, `AmazonElastiCache`, `AmazonRedshift` and `AmazonES`, in every commercial Region the
price list names. Every row is FOCUS shaped, constraint 2: `SkuId`, `SkuPriceId` (the SKU and its
offer term, `RPVSXBK67RKQZAHJ.NQ3QZPMQV9`), `SkuMeter` (the usage type), `PricingUnit`,
`PricingCategory` (Standard for on demand, Committed for a reservation), the currency, the recurring
price, any upfront fee, and `SkuPriceDetails`, which holds the instance type, operating system,
tenancy, capacity status, preinstalled software, licence, engine and volume type a product carries.
A version is one publication of one service's list in one Region, its publication time is the
row's `as_of`, and every row carries `collected_at` beside it, constraint 10.

Built in TASK-P9-004: the adapter, the collector, its schedule, and the reserved terms. Built in
TASK-P9-012: Savings Plans rates for EC2, Compute and EC2 Instance plans, read by the relay
function outside the VPC, the owner's answer to OPEN-17 on 2026-10-07, and stored as `price` rows
under `ComputeSavingsPlans`, Committed, with the plan type as the offering class. Built in
TASK-P9-013: spot prices in every Region the price list sells EC2 in, every zone and product
description, kept as the latest price per pool plus each day's low and high for 90 days, OPEN-18,
spec section 14.7.

## Why it exists

The owner asked on 2026-10-05 for current EC2 and EBS prices, so that Meter can say which machine
to move to, and suggested scraping Vantage's instance site. Research the same day found that the
site is a copy of AWS's own price list and instance data, that its website terms forbid scraping,
and that its MIT licensed scraper reads the same AWS sources Meter can read itself. On 2026-10-07
the owner widened the scope to every commercial Region, reserved, Savings Plans and spot prices, and
the four further services. A saving that is the difference between two real prices cannot be
computed without a catalog, and every price here comes from AWS, never from a third party.

## How it works

`finops_providers/aws/price_list.py`, `AwsPriceCatalog`, reads the Price List Query API through the
hub's endpoint in us-east-1, ADR-0035.

- **Versions.** `ListPriceLists` per service, asked in USD for the current date. A list's ARN ends
  in its version and its Region, and the version is its publication time (`20170901182201` is
  2017-09-01T18:22:01Z, which the real ElastiCache list's own pair confirms), so `as_of` is read
  from the ARN. The Regions are the list's own codes, kept when they have a commercial Region's
  shape; GovCloud, China, the isolated partitions and Local Zones are left out by shape, and no
  Region is named in code, spec section 14.2.
- **Prices.** `GetProducts` per service and Region, a page at a time, as a generator, so no offer
  file and no whole Region is held in memory. EC2 is narrowed at the source to instances at the
  comparable price and to EBS storage; the other four services are read whole by Region, small
  enough to filter afterwards (the ElastiCache list for eu-west-1 holds 506 products, measured on
  2026-10-08).
- **The comparable price.** Shared tenancy, used capacity and no preinstalled software, wherever a
  product carries the attribute. The operating system is kept, not filtered, because a Windows
  instance's smaller size is priced at Windows rates. An Extended Support product, 146 of the 506
  in the real ElastiCache list (measured), is a surcharge on a type rather than its price, so it is
  kept and named with `extendedSupport` and its year in `SkuPriceDetails`.
- **A term.** An upfront fee is the dimension priced per `Quantity`; the other is the recurring
  price. An All Upfront reservation is nought an hour beside its fee, as the real list sells it,
  and is kept.

`finops_ingest/collectors/price_catalog.py`, `PriceCatalogCollector`, runs every 8 hours from its
`collector_schedule` row, ADR-0012, installed for existing tenants by migration 0034. It asks each
service for its versions and loads only a version it does not hold, so a quiet run is five
`ListPriceLists` calls and writes nothing. Each load is a savepoint, writes in batches of 1,000,
records the version's stored row count, and then removes the earlier versions' prices and the
versions left empty, except any price a recommendation quotes, which stays with its version until
the recommendation is written again from a newer one.

**Savings Plans rates**, TASK-P9-012. `finops_providers/aws/savings_plans.py`,
`AwsSavingsPlansRates`, asks `DescribeSavingsPlansOfferingRates` through the relay for EC2 usage in
shared tenancy, one call per plan type and payment option, six a Region, so no single answer holds
a whole Region's rates in the relay's 256 MB (about 13,000 rates a call, modelled). botocore has no
paginator for the call, so the relay follows its `nextToken` itself, up to 200 pages. The API
publishes no version, so a Region's rates are a `PriceSheet` whose version is a digest of the rates,
`sheet_version`: the same rates read again make the same version. `as_of` is the first read of that
set of rates, and the effective date is the day it was read, because the API names neither.
`finops_ingest/collectors/savings_plan_rates.py` reads every Region the price catalog holds EC2 for,
every 8 hours from its schedule row, migration 0036, and stores a sheet only when its version is new,
through the same store and prune steps as the price catalog, so a rate a recommendation quotes
outlives its sheet the same way.

**Spot prices**, TASK-P9-013. `finops_providers/aws/spot.py`, `AwsSpotPrices`, reads
`DescribeSpotPriceHistory` through the relay for a window, one invocation a Region because botocore
pages the call itself: about 2,700 a month across 30 Regions at three runs a day (modelled), the
figure spec section 14.5 gave. EC2 answers a window with each pool's price when it opened and every
change inside it, so every pool arrives each run with the reading's own time as `as_of`.
`finops_ingest/collectors/spot_prices.py` asks each Region for the window since its last read, or
8 hours on a first read, replaces `spot_price` with the newest reading per pool and never with an
older one, and merges each day's low and high into `spot_price_daily`: a reading counts towards the
day it was in effect on, and the price still in effect at the close counts towards that day too.
Daily rows older than 90 days are removed each run and counted in `items_removed`; the schedule row
is migration 0037.

## Failure behaviour

Partial failure is first class, constraint 5. One service in one Region failing rolls back that one
load, is recorded in `sync_error` under `price_catalog` by its typed cause, and leaves the version
already held as the one read. A service whose versions cannot be listed is recorded the same way.
Only a run that read nothing at all fails, so a wholly unreadable catalog is a failed run in the
ledger rather than a green one with errors beside it.

A price is refused with SchemaDrift, never stored and never read as nought: a term whose every
price is nought, a product with no price, a currency other than USD, a term with more than one
recurring price, an unreadable product, ARN or version, or a product priced for another Region.
A Savings Plans rate of nought, a plan length other than one or three years, a currency other
than USD, a rate with no unit, or a rate for another Region is SchemaDrift for that Region's sheet,
and the sheet already held stays. A spot reading of nought, with an unreadable price or time, or in a
zone outside its Region is SchemaDrift for that Region; a Region not opted into is NotOptedIn,
recorded and never a price of nought, constraint 5. A call with more pages than the relay follows is
refused whole,
`RelayPageLimit`, never answered with the pages it reached. `AccessDeniedException` and
`ThrottlingException` are AccessDenied and Throttled; the codes the
Pricing model declares beyond those fall through to SchemaDrift and are pinned in
`tests/providers/aws/test_response_shapes.py`, ISS-215. A Region the list holds nothing for is
NoData, and so is each EC2 query that finds no product, so an instance filter that matched
nothing is a failed Region rather than a Region of volumes alone.

## Security considerations

Read only, constraint 6. The hub task role gains `pricing:ListPriceLists` and
`pricing:GetProducts`, `infra/terraform/hub/iam.tf`, on a wildcard because the Price List API has no
resource level permissions. The data is AWS's public price list and names no customer, account or
person. The tables carry `tenant_id` under the guard's tenant rule like every table, the decision
recorded in migration 0033.

## Interface

`GET /catalog/prices`, TASK-P9-010, filtered by service, Region, SKU, instance type, pricing
category and version, each Region's newest version unless one is named. Every row carries its
version, `as_of` and `collected_at`; the envelope counts coverage in Regions, because the catalog
is about no account, and the route is exportable. The collectors write
`price_list_version` and `price`, migration 0033, and `sync_error`. The `PriceCatalog`,
`SavingsPlansRates` and `SpotPrices` ports, `finops_core/ports/catalog.py`, are held by
`tests/contract/test_catalog_contract.py` to the same assertions for each fake and each adapter over
a stubbed client.

## Not doing

- Every spot reading kept. The owner chose the latest per pool and a daily low and high for 90
  days, OPEN-18, because every reading in every pool grows without limit.
- Savings Plans rates for Fargate, Lambda, SageMaker and the database plans, which no P9 target
  is priced against.
- Dedicated tenancy, capacity reservations and preinstalled software prices, which are not the
  comparable price.
- Data transfer, addresses, snapshots, IOPS and throughput prices. TASK-P9-009 adds the gp3 IOPS
  and throughput prices if the gp2 to gp3 saving needs them.
- Any price from a third party. Vantage's code is a reference for filtering rules only.

## What is not yet proved

Proved offline only, against AWS's own samples: the two responses in the API reference and the
real ElastiCache list for eu-west-1, saved in `tests/providers/aws/extracts`. The Savings Plans rates are
unproved against the API, ISS-263, and so is the size of a Region's spot window, ISS-264. Two things the plan
asks for wait on an account or on the owner, ISS-261: the number of rows a full load stores,
against the ten million spec section 14.4 models, and a real EC2 instance product to hold the EC2
attribute names to. The attribute names used for EC2 instances are the price list documentation's;
the real ElastiCache product and the EBS sample agree with every name they share.

## Status of this document

In build. On demand and reserved prices for the five services were built on 2026-10-08 by
TASK-P9-004, against stubs and AWS's own samples, Savings Plans rates the same day by
TASK-P9-012, and spot prices by TASK-P9-013, against stubs in the shape the botocore model gives. Specified in the
[P9 spec](../specs/2026-10-05-p9-price-catalog-design.md), sections 5.2, 5.3, 7 and 14, and planned in
the [P9 plan](../plans/P9-implementation-plan.md).

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P9.
