# FEAT-030: Config aggregator inventory

| Field | Value |
| --- | --- |
| Sub project | P4 |
| Status | In build |
| Specification | [P4 spec](../specs/2026-09-20-p4-inventory-and-topology-design.md), section 5.1 |
| Tasks | TASK-P4-002, TASK-P4-003, TASK-P4-006, TASK-P4-010 |
| Refresh cadence | 6 hours, plus change driven |

## What it does

Every resource, by region and availability zone, from an organization wide AWS Config aggregator.

## Why it exists

The requirement asked for a list of all resources by zone and region. Writing hundreds of describe loops is a year of work and a rate limit farm, see ISS-013.

## What is already known

Known cost risk: recording all resource types organization wide is a five figure monthly line item, ISS-012. Mitigation is periodic recording for stable types and continuous only for critical ones, stated to stakeholders up front.

## How it works

An organization wide AWS Config aggregator supplies every resource with its region
and availability zone, and most of the relationships FEAT-031 needs.

**Selective recording**, decided 2026-09-20 against ISS-012: continuous recording for
the resource types the graph is built from and the ones carrying cost, and nothing for
types no feature reads. The list lives in `infra/terraform/config/resource_types.tf` so
what is recorded is reviewable in a diff, grouped by the feature that needs each group,
with the four deliberately excluded types and the reason for each.

**What it costs, modelled.** Twenty two resource types, three hundred accounts, two
regions with a recorder, two hundred recorded resources per account and region, and four
configuration items per resource per month, at 0.003 USD per item, is **1,440 USD a
month**. Every figure in that sentence is modelled and none is measured: no recorder has
ever run, ISS-203. `infra/terraform/config/COST.md` carries the working and says which
assumption is least certain, which is the four items per resource: an estate with
autoscaling groups cycling instances is very much more, and at ten the estimate is 3,600
USD. The same estate with `AllSupported` recording is modelled at about 8,600 USD, which
is the five figure line item ISS-012 warns about and the number this decision avoids.

The arithmetic is also in `cost.tf` as locals and in an output, so a plan prints it and a
diff that adds a resource type or a region moves the number where a reviewer sees it.
Constraint 7 tags every resource `finops:module = config`, so the real bill will appear
beside the estimate on the platform cost screen rather than in a console.

**Nothing has been planned and nothing has been applied.** That is what done means for
TASK-P4-010 rather than a caveat on it. `make tf-validate` runs `terraform validate` on
all four stacks and `make lint` runs `fmt -check` on them.

## Failure behaviour

A region that refuses produces a typed cause and does not silently shorten the
result. Every account and region gets a `graph_coverage` row on every run,
including failed ones, and a slice never attempted is `UNREAD` rather than absent.

That distinction matters because an account with genuinely no resources in a region
and an account whose region refused us look identical by row count, and only one is
safe to reason about.

## Security considerations

Read only. The aggregator is in the payer account; the recorders are a member
StackSet.

## Interface

`GET /inventory/resources` and `GET /inventory/topology/coverage`.

## Not doing

**Configuration history.** Config records it and it is a different feature: "what
did this security group look like in March" is drift detection, not topology.
Recording it would also multiply the cost this feature is already careful about.

**Recording every resource type.** ISS-012 says that is a five figure monthly line
item, and the estimate for what is recorded instead is written into the task that
applies it, before it is applied.
