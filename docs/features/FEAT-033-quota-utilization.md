# FEAT-033: Quota utilization per region

| Field | Value |
| --- | --- |
| Sub project | P5 |
| Status | Delivered |
| Specification | [P5 spec](../specs/2026-09-20-p5-quotas-and-limits-design.md), section 5.2 |
| Tasks | TASK-P5-001 to TASK-P5-006 |
| Refresh cadence | 12 hours |

This document said 6 hours until 2026-09-28 and the specification's section 7 said
12. The 12 is right and is the figure in `collector_schedule`: a quota moves when
somebody raises it, which is rare, and usage against it is read as a peak over the
preceding day, so a faster cadence re reads the same window and reports the same
number. The real constraint is the call count, because Service Quotas is rate
limited per account and the collector makes one call per service per account per
region. Corrected here rather than in the schedule, because cadence is data and the
row was already right.

## What it does

Used against limit, per service, per region, for example Ireland and London.

## Why it exists

The requirement asked for quota utilization per zone and region.

## What is already known

Honest constraint: there is no single API for used versus limit across all services. Service Quotas gives limits, the `AWS/Usage` CloudWatch namespace gives usage for a subset, Trusted Advisor covers more, and the remainder needs service specific calls. Coverage is roughly 70 percent, and the gaps are stated rather than hidden. Headroom is a reliability signal, not a cost one.

## How it works

Four sources, and the gaps between them are the feature. Service Quotas gives
limits for every quota. The `AWS/Usage` CloudWatch namespace gives usage for a
subset. Trusted Advisor covers more and needs Business or Enterprise support,
OPEN-03. A few services have their own call. Most quotas in a real estate will
have a limit and no usage.

Headroom is used against limit, and a quota with no usage has no headroom.

Since TASK-P8-013, 2026-10-06, the three tables are `DataTable`s, sortable by any column and still in their own order first: the fullest quota, the unmeasured ones by name, the open requests. None has a total, because each row is a different quota in its own unit.

## Failure behaviour

**A quota with no usage source reports limit known, usage unknown. It never
reports zero.** A product rendering that as nought percent used tells somebody
they have headroom nobody measured, which is constraint 5 with an outage behind it
rather than a wrong number.

The database enforces it: `usage_source = 'NONE'` if and only if `used_value IS
NULL`. A usage figure with no provenance cannot be recorded, and a source cannot
be claimed without a figure.

## Security considerations

Scoped by account and region like every other read. The org reader role gains only
list and get permissions on Service Quotas.

## Interface

`GET /governance/quotas` and `/governance/quotas`. Two lists under two headings:
what can be measured, sorted by headroom, and what cannot, sorted by name with a
reason each. The second is expected to be longer, and its length is the honest
summary of how much of this problem AWS lets anybody solve.

One list with a blank column would be simpler, and a blank sorts somewhere: at the
top it looks urgent, at the bottom it looks safe, and neither is known.

## Not doing

**Predicting when a quota will be hit.** A trend against a limit is a forecast, and
a forecast is governed by ADR-0015's four conditions. It belongs with FEAT-048.
