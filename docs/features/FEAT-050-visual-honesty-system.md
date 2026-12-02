# FEAT-050: Provenance, freshness and failure rendering

| Field | Value |
| --- | --- |
| Sub project | P0 |
| Status | Delivered |
| Specification | [docs/12-UI-DESIGN.md](../12-UI-DESIGN.md) |
| Tasks | TASK-P0-026, TASK-P0-035 |
| Decisions | ADR-0019 |
| Issues addressed | ISS-102, ISS-103, ISS-104, ISS-105 |
| Refresh cadence | Live, reflects whatever the API returns |

## What it does

Makes it impossible to render a number in Meter without also rendering how much
that number is worth trusting: whether it was measured, modelled or forecast,
how old it is, and whether it is a real value or a failure wearing one.

## Why it exists

The data model has 90 lines of constraints making a wrong value impossible to
store. The interface had 18 lines naming five screens.

A constraint stops bad data being stored. Nothing stops a screen presenting
good data misleadingly. Every honesty guarantee in this product is enforced in
the database and then delivered by a pixel, and the database work is worthless
if the last six inches throw it away.

## How it works

**The `Figure` component is the only path a number takes to a screen.** It
requires provenance and freshness as arguments. A screen cannot format a
number itself, so a screen that forgets provenance cannot be built. This is the
same technique as the repository scope guard: make the wrong thing impossible
rather than discouraged.

Provenance is encoded **three times over**, never by colour alone: a fill
treatment, solid for measured and diagonal hatch for modelled, a `~` prefix on
the numeral, and a text label. Colour alone fails for roughly 8 percent of men,
fails in print, and fails in a screenshot pasted into a ticket.

Freshness shows two timestamps, never one. `as_of` is when the data was true
at the source, absolute and precise. `collected_at` is when Meter fetched it,
shown as an age. Staleness is computed against the collector's configured
cadence, so a daily collector six hours old is fine and an hourly one is not.

`StateBoundary` wraps every data surface and implements all seven states:
loading, empty genuine, empty never collected, partial, stale, degraded and
failed.

## Failure behaviour

**This feature is the failure behaviour.** The central rule: a cell whose
collection failed never renders a numeral. Not zero, not a dash, not blank. It
renders the typed cause and the action that fixes it.

`NoData` is the only cause in the taxonomy that renders as a number, because it
is the only one where zero is true.

A column total is never the sum of what happened to succeed. It carries its
denominator: `Total (297 of 300 accounts)`, with the three failures one click
away.

## Security considerations

Scope coverage is persistent in the shell rather than a dismissible banner,
because a banner gets dismissed and the condition does not go away. Complete
coverage states itself: absence of a warning is not confirmation.

Out of scope branches in the organization tree are drawn and marked
unreachable, never pruned, so a partial view is legible as partial.

## Interface

The component inventory in `docs/12-UI-DESIGN.md` section 11. `Figure`,
`StateBoundary`, `CoverageBanner`, `FreshnessIndicator` and `TypedError` are
the five that carry this feature.

## Not doing

No charting beyond the sparkline in P0. P1 introduces charts and must extend
the design system with a chart specific provenance treatment before it does,
because a hatched bar and a hatched line are not the same problem.
