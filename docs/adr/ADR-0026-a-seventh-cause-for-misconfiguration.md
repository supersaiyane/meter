# ADR-0026: A seventh cause, for a value this deployment set that does not exist

Date: 2026-09-28
Status: Accepted

## Context

The error taxonomy has been six causes since P0: `AccessDenied`, `Throttled`,
`NotOptedIn`, `NoData`, `Unreachable` and `SchemaDrift`. Its closedness is the point.
A new cause cannot reach the database without a migration, and that is what stops
every future failure quietly becoming generic, which is the shape every observability
tool degrades into.

`translate` maps three sets of provider codes onto the first three and falls through
to `SchemaDrift`. The fall through is deliberate and the comment on it says why: an
unknown failure rendered as a zero is the defect the whole taxonomy exists to prevent,
so the unknown case is loud rather than quiet.

On 2026-09-28, comparing the error codes each operation declares in the botocore
service model against the three sets `translate` maps found eleven codes across four
operations falling through. Recorded as ISS-215. Nothing was hidden by any of them:
`SchemaDrift` renders as `UNRECOGNISED` and never as a number.

The problem is the word, not the visibility. Four of those eleven are not drift at
all:

- `NoSuchConfigurationAggregatorException`, the AWS Config aggregator named in
  settings. Free text, validated by nothing until the first read, and the single most
  likely first call failure in the product.
- `NoSuchKey` and `NoSuchBucket`, a Terraform state location named in settings.
  FEAT-057 reads what it is told to read, and a path with a typo in it is
  indistinguishable from one that was never created.

Telling an operator their schema has drifted sends them to look for an API change when
the fix is one line of their own configuration. A cause that names the wrong remedy is
worse than a vague one, because a vague one makes somebody look and a wrong one makes
them look in the wrong place.

## Decision

Add `Misconfigured` as the seventh cause, and map only those codes to it.

**The test for membership is whether a person can fix it by editing configuration.**
Not whether the provider said "not found", and not whether the call failed for a
reason we did not expect.

Two boundaries follow from that test and both matter more than the cause itself.

**It is not `NoData`.** A bucket we were told to read and cannot is misconfigured. An
account that genuinely holds no budgets is `NoData`, because we looked and there was
nothing. Collapsing the two would put a configuration error behind a number.

**It is not `SchemaDrift`.** A request we built wrongly, an expression the service
rejected, a parameter it did not accept: those stay where they are. `SchemaDrift` says
we are wrong and `Misconfigured` says the operator is, and blurring them sends somebody
to change a setting that was correct.

It is also not retried. Every other non fatal cause is worth another attempt on the
next cadence. This one produces the identical failure forever until a setting changes,
so retrying only fills the error table.

## Consequences

The vocabulary is mirrored in several places and they move together or not at all:
`finops_core/errors.py`, the `CoverageCause` enum in `finops_core/domain/topology.py`,
the mirror in `finops_api/db/models.py`, three check constraints widened by
`migrations/versions/0018_misconfigured_cause.py`, the `Cause` union and `CAUSE_LABEL`
in `finops-web/src/components/provenance.ts`.

**This paragraph is deliberately not a count.** It said five, and a test found a sixth.
It then said six, and a test found a seventh. Each draft was written by looking, and
looking is what kept being wrong, so what is authoritative is the set of tests below and
not a number in a document:

- `tests/core/test_errors.py`, the closed taxonomy itself.
- `tests/core/test_topology.py` and `tests/db/test_p4_constraints.py`, which refused the
  change until `CoverageCause` carried it. A cause a collector can raise and a coverage
  row cannot record is a slice that fails with no reason attached.
- `tests/db/test_models.py`, the declarative mirror and the two check constraints.
- `tests/contract/test_cause_vocabulary.py`, which crosses the language boundary: the
  Python and TypeScript vocabularies name the same causes, and every cause except
  `NoData` has a label to render.
- `finops-web/src/components/__tests__/surface.test.ts`, the labels a reader sees.

Every one of them failed while this change was being written, and every one was right.
That is the closed taxonomy working exactly as ISS-015 asked, and it is worth recording
that the count in an architecture decision was wrong twice and the tests never were.

Widening a check constraint is the backward compatible direction, so the migration
satisfies constraint 12 in one release rather than three. Old code never writes the new
value and keeps satisfying the wider constraint; new code writes it and the wider
constraint admits it.

**Nothing is backfilled.** Rows already written as `SchemaDrift` were correct under the
vocabulary of the day. Rewriting them to a cause the collector never chose would be
inventing a judgement nobody made, which is the same objection this project raises to
storing a derived value.

The downgrade refuses rather than deletes. A migration that dropped rows to satisfy a
narrower constraint would destroy the record of why a collection failed in order to make
a schema change succeed.

Seven remaining codes still fall through, and they are a different problem: `ServiceFailure`,
`InternalErrorException`, `ExpiredNextTokenException` and `InvalidNextTokenException` are
transient and a retry, not a diagnosis. Mapping them to `Throttled` would be wrong, because
`Throttled` means we are over a quota and would inflate a number somebody reads as one. They
stay pinned by `tests/providers/aws/test_response_shapes.py` and stay open in ISS-215.

## Alternatives considered

**A remediation string on the existing `SchemaDrift`.** Cheaper, structural change of
nothing, and gives an operator the right sentence. Rejected because the cause itself
still reads as drift in every count, every filter and every failure chip, and those are
the surfaces somebody scans before they ever open a detail.

**A generic `Failed`, with the detail carrying everything.** This is the shape the
closed taxonomy exists to prevent, and adopting it here would be the first step of
exactly the degradation ADR-0023 argued against.
