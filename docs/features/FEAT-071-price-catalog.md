# FEAT-071: Price catalog for EC2 and EBS from the AWS Price List, versioned and FOCUS shaped

| Field | Value |
| --- | --- |
| Sub project | P9 |
| Status | Planned |
| Specification | [P9 spec](../specs/2026-10-05-p9-price-catalog-design.md), sections 5.2, 5.3 and 7 |
| Tasks | TASK-P9-004. TASK-P9-010 serves it as `GET /catalog/prices` |
| Refresh cadence | Daily, the `price_catalog` collector, which stops when the stored version is current |

## What it does

Loads list on demand prices for EC2 instances and EBS volumes from AWS's own Price List, for
the two Regions in OPEN-06. Both come from the `AmazonEC2` offer, where EBS is the product
families Storage, Provisioned Throughput and System Operation. Every price row is FOCUS
shaped, constraint 2: `SkuId`, `SkuPriceId` (the AWS RateCode), `ListUnitPrice`,
`PricingUnit`, `PricingCategory` (Standard for on demand), the billing currency and
`SkuPriceDetails`, which holds the operating system, tenancy, capacity status, preinstalled
software and licence. A version is one publication of the offer file, its `publicationDate` is
the row's `as_of`, and every row carries `collected_at` beside it.

## Why it exists

The owner asked on 2026-10-05 for current EC2 and EBS prices, so that Meter can say which
machine to move to, and suggested scraping Vantage's instance site. Research the same day found
that the site is a copy of AWS's own price list and instance data, that its website terms
forbid scraping, and that its MIT licensed scraper reads the same AWS sources Meter can read
itself. No production package holds a catalog today, and a saving that is the difference
between two real prices cannot be computed without one.

## What is already known

Every price comes from AWS, never from a third party: the Price List Query API, filtered to the
two Regions. Vantage's code is a reference for SKU filtering rules, never a data source. One
instance type has many price rows, and filters for Linux, shared tenancy, used capacity and no
preinstalled software choose the comparable one. A zero or missing price is refused with a
typed cause and never stored, and the London file holds zero priced rows for allocated
reservations (measured). `list_unit_price > 0` and `collected_at >= as_of` are database
constraints, a price is unique per Region, `sku_price_id` and version, and each version is a
`price_list_version` row with its row count.

The collector is a `collector_schedule` row with its reason and cost, ADR-0012. Offer files
change irregularly, so each daily run compares the stored version and does no work when it is
unchanged. Files are streamed as CSV with the standard library, so the eu-west-1 JSON,
441,439,512 bytes (measured), is never loaded. Spot prices wait for FEAT-047, Savings Plans and
reserved rate cards are not in the first cut, and which services follow EC2 and EBS is the
owner's call. The Price List answers only in us-east-1, eu-central-1 and ap-south-1, and the hub
cannot reach it today, so nothing here runs until TASK-P9-001 builds the path the owner chose
for OPEN-16 on 2026-10-05, ISS-242.

## Status of this document

Planned. The feature is specified in the
[P9 spec](../specs/2026-10-05-p9-price-catalog-design.md), sections 5.2, 5.3 and 7, and planned
as TASK-P9-004 in the [P9 plan](../plans/P9-implementation-plan.md), both approved by the owner
on 2026-10-05. The sections a built feature carries, how it works, its failure behaviour, its
security considerations, its interface and what it does not do, are written when it is built.
Recording only what is decided is deliberate: a document that invents detail ahead of the
build is worse than a short one, because it will be believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P9.
