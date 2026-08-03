# ADR-0001: Decompose into eight sub projects, build P0 then P2 then P1

Date: 2026-08-23
Status: Accepted

## Context

The requirement set describes nine areas: account onboarding, CUR cost
analysis, utilization and rightsizing, ADFS authentication, resource inventory
and topology, Grafana query cost control, quota utilization, CloudWatch, and
containers, plus a language model angle. These are eight independent
subsystems with different data sources, different deployment models, and
different security postures.

## Decision

Decompose into eight sub projects, each with its own design spec,
implementation plan, and delivery. Build in the order P0, P2, P1, P3, P4 and
P5, P6, P7.

P2, query cost governance, is built second rather than in numeric order.

## Consequences

Positive.

- Each sub project is small enough to be specified precisely and finished.
- P2 second means the fastest visible return, because a working prototype
  already exists and the failure it prevents cost 100,000 USD in one week.
- Sub projects can be resequenced without invalidating the others.

Negative.

- More design documents up front.
- Cross sub project integration is a real risk and needs explicit contracts.
  Mitigated by defining all six provider ports in P0, before any consumer
  exists.

## Alternatives rejected

**One combined specification.** Rejected because the predictable outcome is a
shallow scaffold of all nine areas and a working version of none. This failure
mode is well known when a large requirement set is handed to an implementation
agent as a single unit.

**Strict numeric order, P1 before P2.** Rejected because it delays the only
part of the product with an existing prototype and a proven, quantified cost
event behind it. Building the canonical cost surface first is defensible, but
it postpones the visible win by months.
