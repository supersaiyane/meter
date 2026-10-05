# FEAT-073: Rightsizing to a named, priced target, down and up

| Field | Value |
| --- | --- |
| Sub project | P9 |
| Status | Planned |
| Specification | [P9 spec](../specs/2026-10-05-p9-price-catalog-design.md), sections 5.5 to 5.7 |
| Tasks | TASK-P9-006 to TASK-P9-008. TASK-P9-010 adds the Alternatives table |

## What it does

Every rightsizing recommendation names a target instance type offered in the Region, with the
current and target list prices, the price list version and its publication date, and the
saving as their difference, labelled modelled. Where measured use calls for a bigger machine it
recommends growing instead, as an Upsize with an added monthly cost. The recommendation's
screen shows an Alternatives table of type, vCPUs, memory, network baseline, price per hour and
month, and saving, the chosen target first.

## Why it exists

Meter's rightsizing names no target and overstates the saving, which today is the instance's
monthly cost times its unused fraction. For the planted m5.2xlarge at 7 percent CPU that
reports 90.9 percent of 324.12 USD a month (modelled), when one size down, m5.xlarge, saves 50
percent at measured list prices, and m7g.xlarge would save 57.5 percent (modelled from
measured prices). The owner asked on 2026-10-05 for what lets Meter say which machine to move
to, shrinking or growing.

## What is already known

Compute Optimizer stays the first source of targets, ADR-0006. Its adapter makes one call to
us-east-1 today, with no member account and no `nextToken`, and keeps the first option as text.
It is fixed to call each Region, pass one member account per request, follow `nextToken` and ask
for Graviton through its architecture preference, and every ranked option is kept and priced
from the catalog. Where Compute Optimizer is not enabled or has no answer, Meter's own rule
takes candidates from the same family one or two sizes away, the newer generation, and the
Graviton and AMD variants, each offered in the Region. A candidate fits when CPU p99 times 1.30
is within its vCPUs, memory peak times 1.15, or 1.25 after an out of memory kill, is within its
memory, and network and EBS p99 are within its baseline, never its burst. The cheapest fit is
chosen, snapped to a real type as P6 snaps Fargate sizes. With no agent there is no memory
figure, so only one step down within the family is offered and the rationale says why. Across a
generation or an architecture, the recommendation says vCPUs are not equivalent and Graviton
needs arm64 builds. The metrics today are CPU average and agent memory maximum, with no network
or EBS series, which the fit needs.

The saving is the current list price minus the target's for the hours the instance runs.
Because list is not what an estate pays, it is also shown scaled by the ratio of effective to
list cost for that instance in the bill, and both are labelled modelled with the price version
beside them. The recommendation gains nullable columns for the current `sku_price_id`, the
target type, the target `sku_price_id` and the price version, and a target must name a price
from the same version. CPU or memory p95 above 90 percent, or bandwidth at its baseline, recommends the next
size or a family with more memory per vCPU. An Upsize is a recommendation of its own kind with
an added monthly cost, never a negative saving, so no total of savings can be reduced by it, and
the planted c6i.2xlarge above 90 percent comes out as one. Nothing here reaches AWS until
TASK-P9-001 builds the path the owner chose for OPEN-16 on 2026-10-05, ISS-242.

## Status of this document

Planned. The feature is specified in the
[P9 spec](../specs/2026-10-05-p9-price-catalog-design.md), sections 5.5 to 5.7, and planned as
TASK-P9-006 to TASK-P9-008 in the [P9 plan](../plans/P9-implementation-plan.md), both approved
by the owner on 2026-10-05. The sections a built feature carries, how it works, its failure
behaviour, its security considerations, its interface and what it does not do, are written
when it is built. Recording only what is decided is deliberate: a document that invents detail
ahead of the build is worse than a short one, because it will be believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P9.
