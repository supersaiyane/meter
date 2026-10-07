# ADR-0002: FOCUS 1.1 is the canonical cost schema

Date: 2026-08-23
Status: Accepted. The version was moved to FOCUS 1.4 on 2026-10-08 by ADR-0034; the decision to
adopt FOCUS rather than invent a schema stands as written here

## Context

Meter is AWS first but must support GCP, Azure and PCF later. Cost data from
each provider has a different shape. A naive design normalizes into a bespoke
internal schema, which then has to be extended for every new provider and
becomes the main source of migration pain.

## Decision

Adopt the FinOps Open Cost and Usage Specification, version 1.1, as the
canonical internal cost schema. Normalize at ingest. Do not invent a cost
schema.

Meter specific columns are carried alongside, never inside, the FOCUS
namespace: `tenant_id`, `as_of`, `ingest_run_id`, `source_fingerprint`.

## Consequences

Positive.

- AWS Data Exports emits FOCUS natively. GCP and Azure both publish FOCUS
  exports. Adding a provider becomes a connector, not a schema migration.
- The vocabulary is industry standard, so terminology in the product matches
  terminology in FinOps practice.
- Query and rollup logic is written once and works for every provider.

Negative.

- FOCUS does not cover everything AWS exposes. Provider specific fields still
  need somewhere to live, held in a side table keyed by the same fact.
- FOCUS versions will change and the mapping will need maintenance.

## Alternatives rejected

**A bespoke internal schema.** Rejected because it guarantees a migration for
every provider added, and because the mapping work is the same either way.

**Store raw CUR and normalize at query time.** Rejected because it pushes
provider specific logic into every query, which is exactly the coupling the
port abstraction exists to prevent.
