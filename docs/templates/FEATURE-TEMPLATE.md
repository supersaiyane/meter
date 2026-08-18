# FEAT-nnn: <feature name>

| Field | Value |
| --- | --- |
| Sub project | P<n> |
| Status | Planned \| Specified \| In build \| Delivered |
| Specification | `docs/specs/<file>.md` section <x> |
| Tasks | TASK-P<n>-nnn |
| Decisions | ADR-nnnn |
| Issues addressed | ISS-nnn |
| Refresh cadence | If it collects data. See ADR-0012 |

## What it does

Two or three sentences. What a user can do that they could not before.

## Why it exists

The problem it solves. If the answer is "because it was on the list", the
feature is a candidate for deletion, see ADR-0011 rung one.

## How it works

The mechanism, at the level a new engineer needs to modify it safely. Name the
AWS services, the tables, and the modules involved.

## Data sources and freshness

| Source | Cadence | Best possible freshness |
| --- | --- | --- |

State the difference between `as_of`, when the data was true at the source, and
`collected_at`, when Meter fetched it.

## Measured or modelled

Which figures this feature produces are measured, and which are modelled. If
any figure is modelled, state how its accuracy is checked.

## Failure behaviour

What a user sees when the underlying data cannot be collected. Never a zero,
unless the source genuinely returned no data. See the error taxonomy.

## Security considerations

Permissions required, data sensitivity, and what the scope filter applies to.

## Interface

API routes, MCP tools, and screens.

## Not doing

What this feature deliberately does not cover, and where that lives instead.
