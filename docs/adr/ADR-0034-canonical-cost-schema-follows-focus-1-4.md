# ADR-0034: The canonical cost schema follows FOCUS 1.4, and each ratified version after it

Date: 2026-10-07
Status: Accepted
Supersedes: the version named in constraint 2, FOCUS 1.1, once TASK-P10-006 lands
Relates to: constraint 2, constraint 12, FEAT-004, FEAT-076, the P10 specification

## Context

Constraint 2 says the canonical cost schema is FOCUS 1.1 and forbids inventing one. The
standard has moved on since: 1.2 in June 2025, 1.3 in December 2025 and 1.4 on 2026-06-04.
1.4 removes two columns Meter stores, `ProviderName` and `PublisherName`, replaces them with
`ServiceProviderName` and `HostProviderName`, and adds invoice reconciliation, the one way a
FinOps tool can show its totals agree with the bill. Measured on 2026-10-07, Meter's row
lacks 6 of the 21 columns 1.4 makes mandatory, P10 spec section 4. AWS exports FOCUS 1.2
itself and was among the first data generators certified conformant.

## Decision

**Meter's canonical cost row follows FOCUS 1.4: every Mandatory column, and the conditional
columns a source of Meter's fills.** P10 adds the six mandatory columns Meter lacks and the
two that tie a row to its invoice, backfills the two replacements from the columns 1.4
removes, and keeps those old columns readable until a release after P10, constraint 12.
Constraint 2's text names FOCUS 1.4 in TASK-P10-006, when the code carries it.

**Each ratified version after 1.4 gets a gap note within a month**, measured as P10 spec
section 4 is, and the move to it is planned from that note rather than discovered later.

## Alternatives considered

- **Stay on FOCUS 1.1.** The two columns 1.4 removes would grow stale, and invoice
  reconciliation, the claim the market research found no competitor makes, would be built
  on a schema the standard has already left.
- **Adopt all 65 columns at once.** Most conditional columns have no source Meter reads
  today, so they would be null everywhere and look conformant while saying nothing. They come
  with FOCUS conformance, when a source fills them.
- **Read AWS's FOCUS export and stop normalising CUR 2.0.** Possibly right, and open as
  OPEN-21. The export does not carry the EKS split columns FEAT-035 reads, so it cannot
  replace CUR 2.0 alone.

## What it costs

Two migrations in P10 and a third, later, that drops the old columns. The CUR 2.0
normalisation gains eight columns, each mapped by AWS's published mapping. Tracking each new
version is a standing cost of about one gap note per release, two releases a year so far.

## Why this is an ADR

Constraint 2 is an architectural constraint, and changing the version it names changes what
every collector writes and every screen reads. Undoing it means migrating the row back.

## Consequences

- Migration 0030 adds the columns; a later release drops `provider_name` and
  `publisher_name`.
- `finops_core/domain/cost.py` names FOCUS 1.4 when TASK-P10-002 lands.
- `CLAUDE.md` constraint 2 changes in TASK-P10-006.
- A test reads P10 spec section 4's list of mandatory columns and fails if the row lacks one.
