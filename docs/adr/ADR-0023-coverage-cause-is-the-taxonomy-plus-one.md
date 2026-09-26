# ADR-0023: A coverage cause is the error taxonomy plus one member

Date: 2026-09-26
Status: Accepted

## Context

`graph_coverage` records how much of one account's one region the topology graph
was built from. Its state is `COMPLETE`, `PARTIAL` or `UNREAD`, and the P4 spec
requires a typed cause whenever the state is not `COMPLETE`, so that a banner
saying data is missing can also say why and send somebody somewhere.

`finops_core.errors` holds the six causes a collection can fail with, and
ISS-015 records why there are six and no seventh and no generic one: the moment a
catch all exists it is the cheapest thing to reach for, and within one release
every failure is generic again.

`UNREAD` has no cause among the six. Nothing failed. No read has been attempted,
which is the honest state of every region of every account from enrolment until
the first collector run reaches it. The generated fake estate wrote
`NotYetAttempted` into that column, which is outside the closed taxonomy and
would have failed `tests/core/test_errors.py::test_taxonomy_is_closed` the moment
production code tried to construct it.

Three ways out were available and they are not equally reversible. The value set
lands in a database check constraint, and constraint 12 says migrations are
backward compatible, so widening the set later is a migration and narrowing it is
a migration plus a backfill of rows that no longer validate.

## Decision

`CoverageCause` is a separate `StrEnum` in `finops_core.domain.topology`. Its
members are the six `CollectionError` subclass names verbatim, plus
`NOT_YET_ATTEMPTED` whose value is `NotYetAttempted`.

The values are the class names rather than screaming snake case because a caught
error's `cause` attribute is written straight into the column. A translation
table between the two would be a second place for the six names to live, and the
`cause` property on `CollectionError` exists precisely so there is one.

Three things hold the two sets together:

1. `tests/core/test_topology.py::test_every_taxonomy_cause_is_a_coverage_cause`
   iterates `CollectionError.__subclasses__()` and asserts each name is a member
   here. A seventh cause added to the taxonomy fails the build until this enum has
   seen it.
2. `test_the_only_coverage_cause_outside_the_taxonomy_is_not_yet_attempted`
   asserts the difference is exactly one member, so this enum cannot quietly
   become the generic set the taxonomy refused to be.
3. The `graph_coverage` check constraint lists the same seven values, and
   `tests/migrations` asserts the constraint and the enum agree. A domain enum and
   a check constraint that disagree fail at the first write and not one moment
   before, which is the argument `AccountStatus` already makes in its docstring.

`NoData` and `SchemaDrift` are members although the spec's prose named only four
causes. They are there because the cause arrives from a caught `CollectionError`
and narrowing the set at this boundary would mean mapping an unexpected cause onto
something else, which is the guessing the taxonomy exists to prevent. `NoData`
will not in practice be written: a region that genuinely holds nothing is
`COMPLETE` with zero nodes, which is a different and true statement.

## What was rejected

**Adding `NotYetAttempted` to `finops_core.errors`.** It is not a collection
failure. `CollectionError` is the set of collection failures, every member of it
carries remediation text telling a reader what to do about a failure, and the
remediation for a region nobody has read yet is to wait for the next run. Putting
it there would also put it in every `except CollectionError` in the codebase, and
a collector cannot raise "I have not tried".

**Making the cause column nullable for `UNREAD` only.** This was the cheapest
change and it is the one that loses the most. The check constraint would become
`state = 'COMPLETE' OR state = 'UNREAD' OR cause IS NOT NULL`, which permits a
`PARTIAL` row with no cause for any author who spells the state wrong, and it
gives `NULL` two meanings in one column: nothing to explain, and nothing
attempted. Those two are the exact pair the `availability_zone` docstring in the
same module refuses to conflate, and for the same reason.

**A boolean `attempted` column beside the cause.** Two columns that must agree,
with no constraint able to express the agreement without naming the state anyway.
It also makes every consumer's predicate two clauses long, and the one that gets
written with one clause is the one that renders an unread region as complete.

## Consequences

`CoverageCause` and `CollectionError` are two enumerations of overlapping sets,
which is duplication. It is duplication a test fails on, which is the form of it
worth having. The alternative was duplication that a code review catches, and
three sub projects of evidence in this repository say that is the weaker form.

A seventh collection cause is now a three place change: the taxonomy, this enum,
and a migration that widens the check constraint. The test names the first two.
Nothing names the third, and the migration is the one that fails at runtime
rather than at build time. That is a gap, and it is the same gap ADR-0022 records
about the forbidden import contract's source list.
