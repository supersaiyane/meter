# FEAT-077: Owners from tags, the service catalogue and CloudTrail

| Field | Value |
| --- | --- |
| Sub project | P11 |
| Status | In build |
| Specification | [P11 spec](../specs/2026-10-08-p11-owners-and-savings-ledger-design.md), sections 5.1 to 5.4 |
| Tasks | TASK-P11-001 to TASK-P11-005; TASK-P11-001 to TASK-P11-005 done 2026-10-08 |

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
- **The creator**, CloudTrail's event history by resource name, `LookupEvents` paced to the two
  requests a second AWS documents: the earliest event that created the resource, its verb a
  creating one and its noun the type the resource's ARN names, so a later `CreateTags` is never
  taken for it. A person signed in, or a pipeline's role named as automation. Asked only of a
  resource no tag or catalogue names, at most `creator_lookups_per_run` a run, and once: each
  answer is kept in `creator_lookup`, and one older than the history says so. Weakest.

A recommendation lists them strongest first beside its assigned owner. None is written as an owner.
TASK-P11-001 built the owner types and their rules in `finops_core/domain/ownership.py`, the
`ServiceCatalogue` and `ResourceCreators` ports, and the fakes in `finops_fakes/ownership.py`,
which plant every case in `fake-product-b`, the account with no team tags. TASK-P11-002 built
`resource_owner`, migration 0041 with the same rules as constraints, the `owner_tag_keys` setting,
and the daily `ownership` collector, which writes TAG rows from the inventory's nodes and removes
those it no longer finds; the demo's nodes now carry the estate's own tags. TASK-P11-003 built the
AppRegistry adapter, `finops_providers/aws/appregistry.py`, its network path and permissions, and
the collector's catalogue pass, which keeps an account's rows when its catalogue is refused.
TASK-P11-004 built the CloudTrail adapter, `finops_providers/aws/cloudtrail_creators.py`,
`creator_lookup`, migration 0042, the member role's `cloudtrail:LookupEvents`, and the collector's
creator pass, which keeps a creator's row since who created a resource does not change.
TASK-P11-005 put them on every recommendation, read through each table's own scope rule, and
listed them on the recommendations screen under the owner cell, `OwnerSuggestions`.

## Failure behaviour

Each source fails alone, typed in `sync_error`: a catalogue refused in one account leaves its tags
and creators, and every other account, standing. A failure is never read as "nobody owns this",
and a resource older than the event history is said to be, never guessed. A creator lookup
refused in one account and Region is recorded as asked nowhere, and the rest of that account and
Region waits for the next run. A creating event this cannot read, or whose principal it cannot
name, is SchemaDrift rather than a guessed name. One way it can still be wrong is known: a
resource created by an event this does not recognise reads as older than the history, and the fix
is that event's noun in `CREATES`.

## Security considerations

Read only, constraint 6. Owners are scoped by the account of the resource, `ByAccount`, so a reader
sees owners only for what they can see. A creator's name is a person's identifier and is classed
as such; a pipeline's role is never shown as a person.

## Interface

`owner_suggestions` on every recommendation, each with its source, kind, detail, `as_of` and
`collected_at`, strongest first; `suggested_owner` stays, the strongest team; `created_before`
where CloudTrail found the resource older than its history. The ports are
`finops_core/ports/ownership.py`, held by `tests/contract/test_ownership_contract.py`.

## Not doing

- Writing an owner: a suggestion stays one until a person accepts it, ISS-021.
- Merging two names for one person, which waits on an identity provider, OPEN-01.
- Owners on query findings and anomalies, which keep FEAT-016's.
- A catalogue in a code host, which waits on OPEN-13.
- The creator of a resource no Region holds, an IAM role: the event history is kept Region by
  Region, and the global one is not asked.
- CloudTrail Lake or the organization trail, which reach past 90 days, ISS-122.

## Status of this document

In build. Approved by the owner on 2026-10-08 with AppRegistry, CloudTrail's event history and
teams only. TASK-P11-001 built the owner types, the `ServiceCatalogue` and `ResourceCreators` ports
and the fakes that plant each case; TASK-P11-002 to TASK-P11-004 the tags, the catalogue and the
creators behind them; TASK-P11-005 the suggestions on every recommendation. Specified in the
[P11 spec](../specs/2026-10-08-p11-owners-and-savings-ledger-design.md) and planned in the
[P11 plan](../plans/P11-implementation-plan.md). The sections a built feature carries are written as
its tasks build it.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P11.
