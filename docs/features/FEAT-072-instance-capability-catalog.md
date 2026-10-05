# FEAT-072: Instance capability catalog from DescribeInstanceTypes

| Field | Value |
| --- | --- |
| Sub project | P9 |
| Status | Planned |
| Specification | [P9 spec](../specs/2026-10-05-p9-price-catalog-design.md), sections 5.4 and 7 |
| Tasks | TASK-P9-005. TASK-P9-010 serves it as `GET /catalog/instance-types` |
| Refresh cadence | Daily per Region, the `instance_catalog` collector |

## What it does

Records what each instance type offers in each Region, from EC2's own description of itself:
`DescribeInstanceTypes` and `DescribeInstanceTypeOfferings`, per Region and paged, into
`instance_type_spec`. A row holds the family, the generation and whether it is current, the
architectures, vCPUs, memory, network baseline and peak, EBS baseline and maximum, GPU count,
whether the type is offered in the Region, and `as_of` and `collected_at`. It holds no price;
prices are FEAT-071's.

## Why it exists

A recommendation can name a target only if Meter knows what the target holds and that it is
offered where the instance runs. Today a rightsizing candidate carries `monthly_cost` only,
with no instance type, operating system or tenancy, and a burstable instance gets a flat credit
floor of 20 rather than one relative to its type. FEAT-047 is waiting for an instance catalogue
as well, with on demand and Spot prices.

## What is already known

The API has no burstable baseline field, so baselines and maximum credits come from the table
in the EC2 guide, kept as data with its source, and a test fails when the API lists a burstable
type the table lacks. Positive vCPUs and memory, and a baseline for every burstable type, are
database constraints. The collector is a `collector_schedule` row with its reason and cost,
ADR-0012, daily because new instance types appear between releases, and one Region failing
does not fail the run. The hub has no `ec2` endpoint today, so nothing here runs until
TASK-P9-001 builds the path the owner chose for OPEN-16 on 2026-10-05, ISS-242.

## Status of this document

Planned. The feature is specified in the
[P9 spec](../specs/2026-10-05-p9-price-catalog-design.md), sections 5.4 and 7, and planned as
TASK-P9-005 in the [P9 plan](../plans/P9-implementation-plan.md), both approved by the owner on
2026-10-05. The sections a built feature carries, how it works, its failure behaviour, its
security considerations, its interface and what it does not do, are written when it is built.
Recording only what is decided is deliberate: a document that invents detail ahead of the
build is worse than a short one, because it will be believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P9.
