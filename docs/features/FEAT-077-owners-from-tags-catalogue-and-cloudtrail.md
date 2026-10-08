# FEAT-077: Owners from tags, the service catalogue and CloudTrail

| Field | Value |
| --- | --- |
| Sub project | P11 |
| Status | In build |
| Specification | [P11 spec](../specs/2026-10-08-p11-owners-and-savings-ledger-design.md), sections 5.1 to 5.4 |
| Tasks | TASK-P11-001 to TASK-P11-005; TASK-P11-001 to TASK-P11-003 done 2026-10-08 |

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
OPEN-26, were answered as recommended on 2026-10-08.

## How it works

Three sources, read by the `ownership` collector into `resource_owner`, one row per resource per
source, each with its detail and two timestamps, P11 spec sections 5.1 to 5.4:

- **The catalogue**, AWS AppRegistry: each application, the owner its attribute group names under
  `catalogue_owner_key`, and the tags that mark its resources, `awsApplication` and the stack tag
  CloudFormation adds, since AppRegistry associates stacks and a tag rather than resources; a
  node carrying one is the application's. An owner with an `@` is a person. Strongest.
- **The tags**, under `owner_tag_keys` in `Settings`, `team` unless set: the first key a resource
  carries with a value names its team. Read from the inventory, with no AWS call.
- **The creator**, CloudTrail's event history by resource name: a person, or a pipeline's role named
  as automation. Read once per resource; one older than the history says so. Weakest.

A recommendation lists them strongest first beside its assigned owner. None is written as an owner.
TASK-P11-001 built the owner types and their rules in `finops_core/domain/ownership.py`, the
`ServiceCatalogue` and `ResourceCreators` ports, and the fakes in `finops_fakes/ownership.py`,
which plant every case in `fake-product-b`, the account with no team tags. TASK-P11-002 built
`resource_owner`, migration 0041 with the same rules as constraints, the `owner_tag_keys` setting,
and the daily `ownership` collector, which writes TAG rows from the inventory's nodes and removes
those it no longer finds; the demo's nodes now carry the estate's own tags. TASK-P11-003 built the
AppRegistry adapter, `finops_providers/aws/appregistry.py`, its network path and permissions, and
the collector's catalogue pass, which keeps an account's rows when its catalogue is refused.

## Failure behaviour

Each source fails alone, typed in `sync_error`: a catalogue refused in one account leaves its tags
and creators, and every other account, standing. A failure is never read as "nobody owns this",
and a resource older than the event history is said to be, never guessed.

## Security considerations

Read only, constraint 6. Owners are scoped by the account of the resource, `ByAccount`, so a reader
sees owners only for what they can see. A creator's name is a person's identifier and is classed
as such; a pipeline's role is never shown as a person.

## Interface

`owner_suggestions` on every recommendation, each with its source, kind, detail and `as_of`,
strongest first; `suggested_owner` stays, the strongest team. The ports are
`finops_core/ports/ownership.py`, held by `tests/contract/test_ownership_contract.py`.

## Not doing

- Writing an owner: a suggestion stays one until a person accepts it, ISS-021.
- Merging two names for one person, which waits on an identity provider, OPEN-01.
- Owners on query findings and anomalies, which keep FEAT-016's.
- A catalogue in a code host, which waits on OPEN-13.

## Status of this document

In build. Approved by the owner on 2026-10-08 with AppRegistry, CloudTrail's event history and
teams only. TASK-P11-001 built the owner types, the `ServiceCatalogue` and `ResourceCreators` ports
and the fakes that plant each case. Specified in the
[P11 spec](../specs/2026-10-08-p11-owners-and-savings-ledger-design.md) and planned in the
[P11 plan](../plans/P11-implementation-plan.md). The sections a built feature carries are written as
its tasks build it.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P11.
