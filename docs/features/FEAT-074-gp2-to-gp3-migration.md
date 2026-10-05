# FEAT-074: gp2 to gp3 migration, priced from measured IOPS and throughput

| Field | Value |
| --- | --- |
| Sub project | P9 |
| Status | Planned |
| Specification | [P9 spec](../specs/2026-10-05-p9-price-catalog-design.md), section 5.8 |
| Tasks | TASK-P9-009 |

## What it does

Prices a gp2 volume's move to gp3 from its size and its measured IOPS and throughput. The IOPS
a volume needs is the larger of its gp2 baseline and its measured p99, and the gp3 cost is
storage, plus IOPS above 3,000, plus throughput above 125 MiB/s, each at the catalog's price.

## Why it exists

The owner asked on 2026-10-05 for current EBS prices as well as EC2's. gp3 storage costs less
than gp2, 0.0928 against 0.116 USD per GB month in eu-west-2 (measured), but gp3 includes
3,000 IOPS and 125 MiB/s and charges for more, while gp2 gives 3 IOPS per GiB, from 100 to
16,000, and bursts to 3,000 under 1 TiB. What a move saves depends on what the volume uses, so
it is priced from its measurements rather than from its size alone.

## What is already known

A 1,000 GiB volume needing 250 MiB/s costs 116.00 USD a month on gp2 and 98.60 on gp3, 92.80
for storage plus 5.80 for throughput at 0.0464 USD per MiBps month, a saving of 17.40 (modelled
from measured eu-west-2 prices). Prices come from FEAT-071's catalog, because the `AmazonEC2`
offer holds EBS, and each volume type's included IOPS and throughput, maxima and IOPS per GiB
are kept with their source in `volume_type_spec`. The planted 1000 GiB gp2 volume is priced as
gp3, and its saving is labelled modelled. Nothing here reaches AWS until TASK-P9-001 builds the
path the owner chose for OPEN-16 on 2026-10-05, ISS-242.

## Status of this document

Planned. The feature is specified in the
[P9 spec](../specs/2026-10-05-p9-price-catalog-design.md), section 5.8, and planned as
TASK-P9-009 in the [P9 plan](../plans/P9-implementation-plan.md), both approved by the owner on
2026-10-05. The sections a built feature carries, how it works, its failure behaviour, its
security considerations, its interface and what it does not do, are written when it is built.
Recording only what is decided is deliberate: a document that invents detail ahead of the
build is worse than a short one, because it will be believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P9.
