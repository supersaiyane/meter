# FEAT-006: Typed error taxonomy and data freshness

| Field | Value |
| --- | --- |
| Sub project | P0 |
| Status | Delivered |
| Specification | `docs/specs/2026-08-23-p0-foundation-design.md` section 6 |
| Tasks | TASK-P0-005, 024, 025, 026, 028 |
| Decisions | ADR-0012 |
| Issues addressed | ISS-015, ISS-030 |
| Refresh cadence | Reported on every response |

## What it does

A closed set of six failure causes, and two timestamps on every figure, so a user can always tell the difference between zero, stale, and broken.

## Why it exists

This is the feature that decides whether anyone believes the product. A failed collection rendered as the number zero produces a confidently wrong total, and one of those found by an engineer destroys trust in every other number permanently.

## How it works

Six errors and no more: `AccessDenied`, `Throttled`, `NotOptedIn`, `NoData`, `Unreachable`, `SchemaDrift`. Each carries its scope key, its collector and a human readable remediation. There is deliberately no generic catch all type, because the moment one exists every future failure becomes generic and the taxonomy stops meaning anything. `NoData` is the only cause whose documented rendering is a zero. Every fact carries `as_of`, when the data was true at the source, and `collected_at`, when Meter fetched it. Conflating those two is how a stale number looks fresh. Every API response carries a `meta` block with freshness and a degraded flag.

## Failure behaviour

Governed by the closed error taxonomy in [FEAT-006](FEAT-006-typed-errors-and-freshness.md).
A collection that fails renders as a typed failure with its remediation, never
as the number zero. `NoData` is the only cause that renders as a zero, and only
because the source genuinely returned nothing.

## Security considerations

Read only. Access is filtered by the caller's scope at both the request
dependency and the repository guard, see
[FEAT-007](FEAT-007-authorization-scope-enforcement.md). Every read writes an
audit event recording the scope evaluated.

## Interface

API routes are listed in the specification section 8. MCP tools exposing this
feature are listed in [ADR-0009](../adr/ADR-0009-mcp-alongside-http-api.md).

`/health/freshness` draws each row against its own cadence, added 2026-09-27. The screen already
held the age and the cadence in adjacent columns and left the reader to divide one by the other,
which is the arithmetic the whole page exists to make unnecessary: a daily collector six hours old
is fine and an hourly one six hours old is not.

The track runs from nothing to twice the cadence with the due point in the middle, which is a
third scaling rule and exists because neither of the other two fits. A share of a total is wrong
because collectors do not add up. A fraction of a known maximum is wrong because there is no
maximum: a collector that has not run for a fortnight against an hourly cadence is at three
hundred and thirty six.

Past twice its cadence the bar stops and the end of the track is notched. A collector at nine
times and one at two and a half would otherwise draw identically, and clamping without the mark is
how a chart flattens its worst rows into its merely bad ones. The multiple beside the bar keeps
saying the real figure.

One sentence above the table counts the collectors past their cadence. What cannot be judged is in
neither half of that count and is named separately: a collector nothing schedules cannot be late,
and one that has never succeeded has no age at all. Counting either as late inflates the number
that decides whether somebody investigates, and counting them as current deflates it.

A row with no lateness says which absence it is rather than leaving the cell blank. The two need
different actions, one is fixed by making the collection work and the other by scheduling it, and
a shared sentence would send somebody to the wrong place.

## Not doing

Does not retry on the user's behalf beyond the framework's bounded backoff.
