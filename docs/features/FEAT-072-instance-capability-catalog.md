# FEAT-072: Instance capability catalog for EC2, RDS, ElastiCache, Redshift and OpenSearch

| Field | Value |
| --- | --- |
| Sub project | P9 |
| Status | Delivered |
| Specification | [P9 spec](../specs/2026-10-05-p9-price-catalog-design.md), sections 5.4, 7 and 14 |
| Tasks | TASK-P9-005, done 2026-10-08. TASK-P9-010 serves it as `GET /catalog/instance-types`, done 2026-10-08 |
| Refresh cadence | Every 8 hours, the `instance_catalog` collector |

## What it does

Records what each instance type offers in each Region it is sold in, into `instance_type_spec`:
the family, whether the generation is current, the architectures, vCPUs, memory, network
performance with its baseline and peak in gigabits where AWS publishes them, EBS baseline and
maximum, GPU count, whether the type is still offered, and `as_of` and `collected_at`. A burstable
type also carries its baseline share of a vCPU, the most credits it can accrue, and where those
figures were read. It holds no price; prices are FEAT-071's.

EC2 types come from EC2's own description of itself, `DescribeInstanceTypes`, read once in the
hub's Region and stored in every Region the price list sells each type in. RDS, ElastiCache,
Redshift and OpenSearch classes come from their price list products' attributes, keyed by service
in the same table, spec section 14.3.

## Why it exists

A recommendation can name a target only if Meter knows what the target holds and that it is
offered where the instance runs. A rightsizing candidate carried `monthly_cost` only, with no
instance type, and a burstable instance got a flat credit floor rather than one relative to its
type. TASK-P9-007 and TASK-P9-008 choose targets from this table; FEAT-047 waits on it too.

## How it works

`finops_providers/aws/instance_types.py` holds two adapters for the `InstanceCatalog` port.

- **`AwsInstanceCatalog`** pages `DescribeInstanceTypes` in a Region through the hub's endpoint
  there, ADR-0035. Network baseline and peak are the sum over the type's network cards, and None
  when any card leaves the figure out; t2 publishes none, and None says so rather than a guess.
- **`PriceListInstanceCatalog`** reads one managed service's products for a Region through the
  Pricing endpoint. Only products carrying vCPUs and memory describe a class: 291 of the 493
  instance products in the real ElastiCache list for eu-west-1 do (measured on 2026-10-08), and
  the rest, Extended Support among them, are priced but say nothing of size. Memory is read from
  `6.38 GiB` or a whole `memoryGib`; the architecture is the processor the product names, or else
  the family's name, a `g` after the generation being Graviton. `as_of` is the list's publication.

**Burstable baselines** are the EC2 guide's credit table, `finops_providers/aws/burstable.py`, read
on 2026-10-08 with its URL stored beside every baseline. The table checks itself on import against
the guide's two formulas, credits earned are the baseline times the vCPUs times 60, and the accrual
limit is 24 hours of them. A managed class such as `db.t3.micro` takes the row of the EC2 type it is
named after, and its source says so.

`finops_ingest/collectors/instance_catalog.py`, `InstanceCatalogCollector`, runs every 8 hours from
its `collector_schedule` row, installed for existing tenants by migration 0035.

- **EC2** is described in the hub's Region and each type stored in every Region the `price` rows
  sell it in, so no Region is named in code; before any prices are held, the hub's Region alone.
- **Held, not trusted.** When a second Region is configured its description is read too, and a
  type described differently there is SchemaDrift in `sync_error` and is stored only in the hub's
  Region. The hub reaches EC2 in eu-west-1 and eu-west-2, ADR-0035, which makes eu-west-2 the
  natural second Region; the composition that will pass it does not exist yet.
- **The managed services** are read only in a Region whose price list version is newer than the
  description held, so a quiet run reads nothing for them. EC2's rows are rewritten each run,
  because a description carries no version: about 900 types in about 30 Regions (modelled).
- **Withdrawn types** are set `offered = false`, never deleted, because a recommendation may still
  name one.

## Failure behaviour

Partial failure is first class, constraint 5. A Region or a service that cannot be read is
recorded in `sync_error` under `instance_catalog` by its typed cause and the rest is stored; only a
run that read nothing at all fails. Three shortfalls inside a read that succeeded are recorded and
do not fail it: a burstable type with no row in the credit table, NoData and not stored, because
the database refuses a burstable type without a baseline, constraint 11; a type the price list
sells that the hub's Region does not describe, NoData; and a type the second Region describes
differently, SchemaDrift. A description with no vCPUs, memory or architecture, or a network or EBS
maximum below its baseline, is SchemaDrift, refused in the domain before it can reach a constraint.

## Security considerations

Read only, constraint 6. The hub task role gains `ec2:DescribeInstanceTypes`,
`infra/terraform/hub/iam.tf`, on a wildcard because a describe call takes no resource level
permission; the price list reads are FEAT-071's. The data is AWS's public description of its
products and names no customer, account or person. The table carries `tenant_id` under the
guard's tenant rule like every table, migration 0033.

## Interface

`GET /catalog/instance-types`, TASK-P9-010, filtered by service, Region, family, architecture,
vCPUs and memory, offered types only unless asked, with a type's baseline and its source. Coverage
is counted in Regions and the route is exportable. The collector writes
`instance_type_spec` and `sync_error`. The `InstanceCatalog` port, `finops_core/ports/catalog.py`,
is held by `tests/contract/test_catalog_contract.py` to the same assertions for the fake and for
`AwsInstanceCatalog` over a stubbed client.

## Not doing

- `DescribeInstanceTypeOfferings`. Where a type is sold is read from the price list instead, spec
  section 14.3, which needs no call into every Region.
- Instance storage, accelerators other than GPUs, and placement features, which no target choice
  in P9 reads.
- A baseline for a burstable type the guide's table lacks. It is named in `sync_error` instead.

## What is not yet proved

Proved offline, against EC2's real `t2.micro` description, the real ElastiCache list for
eu-west-1, the botocore model, and the EC2 guide's table. Waiting on ISS-262: two real Regions'
descriptions compared, and the RDS, Redshift and OpenSearch attribute names, which no real product
in this repository shows.

## Status of this document

Delivered on 2026-10-08 against fakes, proven by TASK-P9-011. Built that day by TASK-P9-005,
against stubs and AWS's own samples. Specified in
the [P9 spec](../specs/2026-10-05-p9-price-catalog-design.md), sections 5.4, 7 and 14, and planned
in the [P9 plan](../plans/P9-implementation-plan.md).

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P9.
