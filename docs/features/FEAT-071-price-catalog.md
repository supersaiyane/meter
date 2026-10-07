# FEAT-071: Price catalog from AWS for EC2, EBS, RDS, ElastiCache, Redshift and OpenSearch, every Region and price type, versioned and FOCUS shaped

| Field | Value |
| --- | --- |
| Sub project | P9 |
| Status | In build |
| Specification | [P9 spec](../specs/2026-10-05-p9-price-catalog-design.md), sections 5.2, 5.3, 7 and 14 |
| Tasks | TASK-P9-004, on demand and reserved, done 2026-10-08. TASK-P9-012, Savings Plans rates, and TASK-P9-013, spot, to come. TASK-P9-010 serves it as `GET /catalog/prices` |
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

Built in TASK-P9-004: the adapter, the collector, its schedule, and the reserved terms. Savings
Plans rates, TASK-P9-012, and spot prices, TASK-P9-013, are still to come, read by the relay
function outside the VPC, the owner's answer to OPEN-17 on 2026-10-07, and spot is kept as the
latest price per pool plus each day's low and high for 90 days, OPEN-18, spec section 14.7.

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

## Failure behaviour

Partial failure is first class, constraint 5. One service in one Region failing rolls back that one
load, is recorded in `sync_error` under `price_catalog` by its typed cause, and leaves the version
already held as the one read. A service whose versions cannot be listed is recorded the same way.
Only a run that read nothing at all fails, so a wholly unreadable catalog is a failed run in the
ledger rather than a green one with errors beside it.

A price is refused with SchemaDrift, never stored and never read as nought: a term whose every
price is nought, a product with no price, a currency other than USD, a term with more than one
recurring price, an unreadable product, ARN or version, or a product priced for another Region.
`AccessDeniedException` and `ThrottlingException` are AccessDenied and Throttled; the codes the
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

No route yet; TASK-P9-010 serves the catalog as `GET /catalog/prices`. The collector writes
`price_list_version` and `price`, migration 0033, and `sync_error`. The `PriceCatalog` port,
`finops_core/ports/catalog.py`, is held by `tests/contract/test_catalog_contract.py` to the same
assertions for the fake and for this adapter over a stubbed client.

## Not doing

- Savings Plans rates and spot prices, which are TASK-P9-012 and TASK-P9-013.
- Dedicated tenancy, capacity reservations and preinstalled software prices, which are not the
  comparable price.
- Data transfer, addresses, snapshots, IOPS and throughput prices. TASK-P9-009 adds the gp3 IOPS
  and throughput prices if the gp2 to gp3 saving needs them.
- Any price from a third party. Vantage's code is a reference for filtering rules only.

## What is not yet proved

Proved offline only, against AWS's own samples: the two responses in the API reference and the
real ElastiCache list for eu-west-1, saved in `tests/providers/aws/extracts`. Two things the plan
asks for wait on an account or on the owner, ISS-261: the number of rows a full load stores,
against the ten million spec section 14.4 models, and a real EC2 instance product to hold the EC2
attribute names to. The attribute names used for EC2 instances are the price list documentation's;
the real ElastiCache product and the EBS sample agree with every name they share.

## Status of this document

In build. On demand and reserved prices for the five services were built on 2026-10-08 by
TASK-P9-004, against stubs and AWS's own samples. Specified in the
[P9 spec](../specs/2026-10-05-p9-price-catalog-design.md), sections 5.2, 5.3, 7 and 14, and planned in
the [P9 plan](../plans/P9-implementation-plan.md).

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P9.
