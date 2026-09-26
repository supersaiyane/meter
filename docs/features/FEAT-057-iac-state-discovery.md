# FEAT-057: Which file manages this resource

| Field | Value |
| --- | --- |
| Sub project | P4 |
| Status | Specified |
| Specification | [competitive review](../11-COMPETITIVE-REVIEW.md), 2026-09-26 candidate list |
| Tasks | `TASK-P4-013` |
| Refresh cadence | Follows FEAT-030 |
| Source | Adopted from the IBM Turbonomic review on 2026-09-26 |

## What it does

Records, per resource, whether infrastructure as code manages it and which state file and
address own it. Read from Terraform state, attached to `topology_node`.

## Why it exists

FEAT-040 generates a remediation as a pull request and cannot produce a useful one without
knowing which file to change. It is also worth having on its own: a resource nobody manages in
code is a fact somebody wants to know, independently of any remediation.

Recorded in P4 rather than with FEAT-040 in P7 because who manages a resource is an inventory
fact about that resource, belonging beside its region and its zone. FEAT-040 is a consumer.
P7 has no plan and no approved specification, and writing tasks into one would be the guess
`docs/plans/README.md` warns about.

## How it works

Terraform state holds a resource address and a provider identifier, and that identifier is the
ARN `topology_node` already keys on. The backend location is configuration, not discovery.

## Failure behaviour

The field is three valued and the default is **not determined**, never unmanaged. Unmanaged is
an actionable fact and "we did not look in the right bucket" is not, and rendering the second
as the first would tell somebody to import a resource that is already inside a module.

## Security considerations

Read only, constraint 6. The backend location is configured rather than discovered, because
guessing at buckets is reconnaissance. No credential for a customer state backend lives in
this repository, and the scan gate covers the new configuration.

## Interface

The entity page, FEAT-053, shows the address where there is one and says not determined where
there is not.

## Not doing

Writing a pull request, which is FEAT-040. Reading CloudFormation or CDK: one format first,
and the port is shaped so that a second is an adapter rather than a rewrite.
