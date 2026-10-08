# FEAT-073: Rightsizing to a named, priced target, down and up

| Field | Value |
| --- | --- |
| Sub project | P9 |
| Status | In build |
| Specification | [P9 spec](../specs/2026-10-05-p9-price-catalog-design.md), sections 5.5 to 5.7 |
| Tasks | TASK-P9-006, Compute Optimizer's targets kept and priced, TASK-P9-007, Meter's own downsizing target, and TASK-P9-008, the Upsize, and TASK-P9-010, the Alternatives table, done 2026-10-08 |

## What it does

Every rightsizing recommendation names a target instance type offered in the Region, with the
current and target list prices, the price list version, and the saving as their difference,
labelled modelled. Where measured use calls for a bigger machine it recommends growing instead,
as an Upsize with an added monthly cost. The recommendation's screen shows an Alternatives table
of type, vCPUs, memory, network baseline, price per hour and month, and saving, the chosen
target first.

Built in TASK-P9-006: Compute Optimizer's findings carry every option it ranked, each with its
rank, its performance risk, its own monthly saving, the migration effort and the platform
differences, and each priced from the catalog or kept saying why not. A Compute Optimizer
recommendation names its first ranked option as its target, with both prices from one catalog
version. Built in TASK-P9-007: Meter's own rightsizing names the cheapest type that fits and quotes
the price difference. Built in TASK-P9-008: an instance under pressure is an Upsize, a
recommendation of its own kind naming the cheapest larger type that fits, with what it adds to the
bill a month and a saving of nought.

## Why it exists

Meter's rightsizing named no target and overstated the saving, which was the instance's monthly
cost times its unused fraction. For the planted m5.2xlarge at 7 percent CPU that reports 90.9
percent of 324.12 USD a month (modelled), when one size down, m5.xlarge, saves 50 percent at
measured list prices, and m7g.xlarge would save 57.5 percent (modelled from measured prices). The
owner asked on 2026-10-05 for what lets Meter say which machine to move to, shrinking or growing.

## How it works

**Compute Optimizer, read properly**, P9 spec section 5.5 and ADR-0006.
`finops_providers/aws/recommendations.py` reads `GetEC2InstanceRecommendations` in each Region the
settings name, for each member account in its own request, follows `nextToken` itself because
botocore has no paginator for the call, and asks for Graviton through the CPU architecture
preference. Every option is kept as a `RankedOption`; an option with no performance risk, or one
off the scale of nought to four, is SchemaDrift. One account or Region that cannot be read is
returned beside what was read, `ScopedFindings`.

**Priced from the catalog.** `finops_ingest/collectors/recommendations.py` replaces a
recommendation's options in `recommendation_option` on each read and prices each at the catalog's
newest EC2 version for its Region, at the Linux on demand comparable price: shared tenancy, used
capacity, nothing preinstalled, no licence, and not an Extended Support surcharge. An option the
catalog cannot price is kept with the reason, either no price list for the Region or no such
price in it. The recommendation's `current_sku_price_id`, `target_instance_type`,
`target_sku_price_id` and `price_version` are set from the same version, the target being the
first ranked option, so a saving can only be the difference of two prices that exist together.
The recommendation's own saving stays Compute Optimizer's figure for its first option.

**Meter's own target**, TASK-P9-007, where Compute Optimizer has no answer.
`finops_query/targets.py` holds the rule, pure: candidates are the same family one or two sizes
down, and the newer generations of the same series with their AMD and Graviton variants at the
same size or one or two down, offered in the Region and priced; a burstable type is only replaced
by a burstable one. A candidate fits when CPU p99 times 1.30 is within its vCPUs, the memory peak
times 1.15, or 1.25 after an out of memory kill, within its memory, and network and EBS p99 within
its baselines, never its burst; a baseline the target does not publish is not checked and the
rationale says so. Without an agent there is no memory figure, so only one size down within the
family is offered, and the rationale says why. The cheapest fit is chosen.
`finops_ingest/collectors/waste_compute.py` reads network and EBS bytes beside CPU and memory, puts
each CPU rightsizing through the rule against the catalog's offers for its Region and operating
system, `finops_ingest/collectors/catalog_reads.py`, and quotes the saving as the two list prices'
difference for the hours the instance runs, counted from its hourly points, and as the bill pays,
scaled by what the bill shows over list for those hours and never scaled up. Both are modelled, and
the rationale names both prices, the hours and the price version. The planted m5.2xlarge at 7
percent CPU with no agent is offered m5.xlarge and saves about half its cost (modelled), no longer
90.9 percent of it. Across a generation or an architecture the rationale says vCPUs are not
equivalent, and a Graviton target that arm64 builds are needed.

**The Upsize**, TASK-P9-008, spec section 5.7. Where a shrink is refused and the instance has
history enough and no burstable credits to lean on, CPU or memory p95 above 90 percent, or network
p99 at the type's baseline, is pressure. `finops_query/targets.py` takes the next size up in the
family, or a newer generation of it, with the same processor, and where memory is the pressure a
type of the same size with more memory per vCPU, and names the cheapest that fits the demand with
the same headroom as a shrink. The recommendation is `UPSIZE_INSTANCE`, its saving nought and its
`added_monthly_cost` the two list prices' difference for the hours run, scaled to the bill, both
modelled; its severity is read from that added cost. The database holds the kind and the cost
together, migration 0039, and the Overview's savings by category leaves an Upsize out, so no total
of savings falls because of one. The planted c6i.2xlarge above 90 percent CPU is an Upsize to
c6i.4xlarge.

## Failure behaviour

One account or Region that cannot be read is recorded in `sync_error` under `recommendations` by
its typed cause, the rest is stored, and only findings in the scopes that were read can be
withdrawn: a finding in an account that timed out stays open rather than being dismissed,
constraint 5. Every scope failing raises the cause, and NotOptedIn everywhere is the service not
being enabled, ISS-004, recorded as nothing to withdraw. More than 100 pages for one account in
one Region is SchemaDrift for that scope. An unpriced option is never a price of nought: the
database refuses an option with neither a price nor a reason, migration 0038. For Meter's own
rightsizing, no cheaper type that fits is a refusal recorded in `sizing_refusal` with the reason,
never a recommendation; a saving under the 5 USD floor is refused the same way. Where the
instance's type is not known, the catalog does not describe it, or the catalog holds no prices for
the Region, the old estimate stands, the unused share of the bill, and its rationale says why no
target is named. A target that stops fitting is cleared on the next run. An instance under
pressure with no type, no catalog or no larger type that fits is recorded in `sizing_refusal` as
an `UPSIZE_INSTANCE` refusal saying what it is short of and why nothing could be named.

## Security considerations

Read only, constraint 6. Compute Optimizer is read with the role the composition gives it, one
member account a request; no new permission is added here. `recommendation_option` is scoped
through its recommendation by the guard, as `recommendation_event` is, so a reader who may not
see a finding cannot see what it was compared with.

## Interface

Every recommendation carries `current_instance_type`, `target_instance_type`, both list prices
an hour from its `price_version`, and an Upsize's `added_monthly_cost`, TASK-P9-010; its saving is
the difference already scaled to the bill. `GET /waste/recommendations/{id}/alternatives` lists what
it was compared with, the chosen type first, each sized from the catalog and priced an hour and a
month at 730 hours, at list and modelled, or saying why it has no price; it is exportable. The
recommendations screen names the target in its Target column and shows the Alternatives table under
one finding. Compute Optimizer's options come from its ranking; Meter's are every type its rule
found to fit the demand it measured, cheapest first, written by `waste_compute` when it judges
them, because the demand is not stored and a list worked out later could not say which types fit,
OPEN-24. They carry no performance risk, which migration 0040 allows rather than inventing a
nought. The collectors write `recommendation_option` and the recommendation's four price columns.
`RecommendationSource.compute_optimizer` returns `ScopedFindings`, which iterates as its findings,
so the fake and any caller that knows nothing of scopes read it as before.

## Not doing

- Pricing Compute Optimizer's options at the instance's own operating system, which it does not
  name; they are quoted at Linux. Meter's own targets are quoted at the operating system the
  candidate carries, Linux where the inventory names none.
- Scaling out an Auto Scaling group instead of growing a type; a group is sized at group level,
  FEAT-047.
- Listing a type Meter's rule found not to fit as an alternative; the rationale names why the
  cheaper ones were refused when none fits.
- Writing to Compute Optimizer: its preferences are asked per request and never stored at AWS,
  constraint 6.

## What is not yet proved

The Compute Optimizer shapes are the botocore 1.43.108 model's, held by
`tests/providers/aws/test_response_shapes.py`, and its answers are recorded, not real, ISS-122.
The member account list comes from the organization tree at composition, which nothing assembles
yet, ISS-182.

## Status of this document

In build. TASK-P9-006 to TASK-P9-008 and TASK-P9-010 were built on 2026-10-08; TASK-P9-011 proves
it end to end. Specified in the
[P9 spec](../specs/2026-10-05-p9-price-catalog-design.md), sections 5.5 to 5.7, and planned in the
[P9 plan](../plans/P9-implementation-plan.md).

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P9.
