# FEAT-077: Owners from tags, the service catalogue and CloudTrail

| Field | Value |
| --- | --- |
| Sub project | P11 |
| Status | Planned |
| Specification | [P11 spec](../specs/2026-10-08-p11-owners-and-savings-ledger-design.md), sections 5.1 to 5.4 |
| Tasks | TASK-P11-001 to TASK-P11-005 |

## What it does

Reads the owners an estate already names for each resource: the service catalogue's application
owner, the first of the deployment's owner tag keys the resource carries, and the principal of the
CloudTrail event that created it. Each is kept with its source, `as_of` and `collected_at`, and
every recommendation shows them as suggestions beside the owner a person assigned, strongest
first. A suggestion never becomes an owner without a person accepting it.

## Why it exists

An unowned finding is never fixed, ISS-021. Meter suggests an owner today only from one tag key,
`team`, read per request and never stored, CHG-0126. An estate whose owners live under another
key, in AWS AppRegistry, or only in who created a resource gets no suggestion at all.

## What is already known

AppRegistry's `ListApplications`, `ListAssociatedResources`, `ListAttributeGroupsForApplication`
and `GetAttributeGroup`, and CloudTrail's `LookupEvents` by `ResourceName`, are all in the
botocore 1.43.108 model (measured on 2026-10-08). A creator that is an assumed role session is a
pipeline, named as automation and never as a person. A resource older than CloudTrail's event
history says so rather than being guessed. Which catalogue, OPEN-25, and which CloudTrail store,
OPEN-26, are put to the owner with their recommendations.

## Status of this document

Planned. Specified in the [P11 spec](../specs/2026-10-08-p11-owners-and-savings-ledger-design.md)
and planned as TASK-P11-001 to TASK-P11-005 in the [P11 plan](../plans/P11-implementation-plan.md),
on 2026-10-08, waiting for the owner's approval to build. The sections a built feature carries are
written when it is built.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P11.
