# FEAT-074: gp2 to gp3 migration, priced from measured IOPS and throughput

| Field | Value |
| --- | --- |
| Sub project | P9 |
| Status | In build |
| Specification | [P9 spec](../specs/2026-10-05-p9-price-catalog-design.md), section 5.8 |
| Tasks | TASK-P9-009, done 2026-10-08. TASK-P9-011 proves it end to end |

## What it does

Prices an attached gp2 volume's move to gp3 from its size and its measured IOPS and throughput,
and writes it as an `EBS_GP2_TO_GP3` recommendation whose rationale states the sum. gp3 is given
the larger of what gp2 gives the volume and what the volume was measured to use, for IOPS and for
throughput, and is costed as storage, plus IOPS above 3,000, plus MiB/s above 125, each at the
catalog's price for the volume's Region.

## Why it exists

The owner asked on 2026-10-05 for current EBS prices as well as EC2's. gp3 storage costs less
than gp2, 0.0928 against 0.116 USD per GB month in eu-west-2 (measured), but gp3 includes 3,000
IOPS and 125 MiB/s and charges for more, while gp2 gives 3 IOPS per GiB and up to 250 MiB/s. What
a move saves depends on what the volume needs, so it is priced from its measurements and its size
rather than from its size alone.

## How it works

**The rule**, `finops_query/volumes.py`, no database and no clock. gp2 gives a baseline of 3 IOPS
per GiB, never under 100 nor over 16,000, and 128 MiB/s at 170 GiB and below, 250 above. gp3
must give the larger of that and the p99 measured, a figure not measured taken at what gp2 gives
and said in the rationale. The EBS user guide's gp3 limits, read on 2026-10-08, hold it: at most
80,000 IOPS and 2,000 MiB/s, IOPS above the included 3,000 at most 500 per GiB, and throughput at
most 0.25 MiB/s per IOPS, so throughput above 750 MiB/s buys IOPS of its own. A volume gp3 cannot
match, or a gp3 that costs no less, is a sentence saying why. The guide's earlier maxima, 16,000
IOPS and 1,000 MiB/s, were superseded by the time it was read.

**The prices.** The `AmazonEC2` price list holds EBS. The adapter asks for its Storage family as
before and now for System Operation and Provisioned Throughput, gp3's IOPS and throughput, keeping
a product of those families only when it names a volume type and recording the family in the
price's details. Those two queries may come back empty: a Region selling neither loses only this
comparison, which says which price is missing, where an empty instance query is NoData for the
Region. `catalog_reads.volume_prices` reads the four prices from the newest EC2 version for the
Region, the one an instance's target is priced from, by the unit each is sold in.

**The figures, stored.** No AWS call describes a volume type's limits, so the instance catalog
collector writes the rule's own figures for gp2 and gp3 into `volume_type_spec` on every run, with
the guide's page and the day it was read as their source. One definition, shown where it is used.

**The pass.** `waste_compute` is given the estate's attached volumes beside its instances. The
gp2 ones join the same GetMetricData batch with `VolumeReadOps`, `VolumeWriteOps`,
`VolumeReadBytes` and `VolumeWriteBytes` as hourly sums; IOPS and MiB/s are the p99 of read and
write together per second. `waste_volumes` prices each and returns the recommendation or the
refusal. The saving is gp2's monthly cost less gp3's, both at list, scaled to what the bill shows
for the volume and never up, and both are modelled. A saving under the 5.00 USD floor every waste
rule uses is a refusal with the figure. The recommendation names no instance type or price id;
the working in its rationale, with the price list version, is how it is checked.

**The planted case.** `amazonebs/fake-platform-b/0002`, 1,000 GiB of gp2, publishes operations,
about 19 a second at its busiest (modelled), and no bytes. gp3 is given gp2's 3,000 IOPS and 250
MiB/s, the throughput said to be unmeasured, and at the fake catalog's invented prices costs 85.00
a month against 100.00 on gp2: a saving of 15.00 (modelled).

## Failure behaviour

- No EC2 version in the catalog for the Region: a refusal in `sizing_refusal`, saying so.
- A version without gp3's IOPS or throughput price, as one loaded before 2026-10-08 is: a refusal
  naming the missing prices. The next version loaded carries them.
- A volume publishing neither operations nor bytes: counted unobserved in `sync_error`, never
  judged, because absent is not nought.
- A throughput price labelled per GiB/s is read as per MiB/s and never divided, ISS-265: if the
  label is right that makes gp3 dearer and the move is refused, never a saving overstated.

## Security considerations

Read only, constraint 6. The EBS metrics are read with the role and the batch the instance pass
already uses, and the prices come from the catalog Meter stores; no permission is added. The
recommendation is scoped by its account like every other.

## Interface

No route of its own. The recommendation appears with the others, `EBS_GP2_TO_GP3`, source
`METER`, with the working in its rationale. `volume_type_spec` holds the figures, which
TASK-P9-010's catalog routes may serve.

## Not doing

- io1, io2, st1 and sc1: only gp2 has a gp3 move to price.
- An unattached volume: it publishes nothing, and what it needs is deleting, which the unattached
  rule says from its configuration.
- Matching gp2's burst credit behaviour hour by hour: gp3 is given at least what gp2 can give,
  which is never less than the burst a gp2 volume under 1 TiB can reach.

## What is not yet proved

The unit of gp3's throughput price in a real price list, ISS-265. The EBS series are read through
the same GetMetricData batch as the instances', whose real answers are recorded rather than live,
ISS-002. No production inventory names the estate's volumes yet; the demo seed and the tests do.

## Status of this document

In build. TASK-P9-009 was built on 2026-10-08, and TASK-P9-011 proves it end to end. Specified in
the [P9 spec](../specs/2026-10-05-p9-price-catalog-design.md), section 5.8, and planned in the
[P9 plan](../plans/P9-implementation-plan.md).

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P9.
