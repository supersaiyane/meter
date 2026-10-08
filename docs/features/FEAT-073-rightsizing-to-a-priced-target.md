# FEAT-073: Rightsizing to a named, priced target, down and up

| Field | Value |
| --- | --- |
| Sub project | P9 |
| Status | In build |
| Specification | [P9 spec](../specs/2026-10-05-p9-price-catalog-design.md), sections 5.5 to 5.7 |
| Tasks | TASK-P9-006, Compute Optimizer's targets kept and priced, done 2026-10-08. TASK-P9-007 and TASK-P9-008 to come. TASK-P9-010 adds the Alternatives table |

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
version. Meter's own rule where Compute Optimizer has no answer, TASK-P9-007, and the Upsize,
TASK-P9-008, are still to come.

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
The recommendation's own saving stays Compute Optimizer's figure for its first option until
TASK-P9-007 quotes the price difference.

## Failure behaviour

One account or Region that cannot be read is recorded in `sync_error` under `recommendations` by
its typed cause, the rest is stored, and only findings in the scopes that were read can be
withdrawn: a finding in an account that timed out stays open rather than being dismissed,
constraint 5. Every scope failing raises the cause, and NotOptedIn everywhere is the service not
being enabled, ISS-004, recorded as nothing to withdraw. More than 100 pages for one account in
one Region is SchemaDrift for that scope. An unpriced option is never a price of nought: the
database refuses an option with neither a price nor a reason, migration 0038.

## Security considerations

Read only, constraint 6. Compute Optimizer is read with the role the composition gives it, one
member account a request; no new permission is added here. `recommendation_option` is scoped
through its recommendation by the guard, as `recommendation_event` is, so a reader who may not
see a finding cannot see what it was compared with.

## Interface

No route yet; TASK-P9-010 adds the Alternatives table and the target on the recommendation's
screen. The collector writes `recommendation_option` and the recommendation's four price columns.
`RecommendationSource.compute_optimizer` returns `ScopedFindings`, which iterates as its findings,
so the fake and any caller that knows nothing of scopes read it as before.

## Not doing

- Pricing at the instance's own operating system. Linux is the comparable price until
  TASK-P9-007 reads the instance's own from its bill line.
- Meter's own targets where Compute Optimizer has no answer, TASK-P9-007, and the Upsize,
  TASK-P9-008.
- Writing to Compute Optimizer: its preferences are asked per request and never stored at AWS,
  constraint 6.

## What is not yet proved

The Compute Optimizer shapes are the botocore 1.43.108 model's, held by
`tests/providers/aws/test_response_shapes.py`, and its answers are recorded, not real, ISS-122.
The member account list comes from the organization tree at composition, which nothing assembles
yet, ISS-182.

## Status of this document

In build. TASK-P9-006 was built on 2026-10-08. Specified in the
[P9 spec](../specs/2026-10-05-p9-price-catalog-design.md), sections 5.5 to 5.7, and planned in the
[P9 plan](../plans/P9-implementation-plan.md).

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P9.
