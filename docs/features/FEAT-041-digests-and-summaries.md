# FEAT-041: Per team digests and executive summaries

| Field | Value |
| --- | --- |
| Sub project | P7 |
| Status | Delivered |
| Specification | [P7 spec](../specs/2026-09-28-p7-insight-and-llm-layer-design.md), sections 6.2 and 9 |
| Tasks | TASK-P7-012 |
| Refresh cadence | Weekly |

## What it does

A weekly per team digest and an executive summary, written from the data rather than from a template.

## Why it exists

A finding that reaches nobody changes nothing.

## What is already known

Every figure carries its provenance and its measured or modelled flag.

## How it works

**As built, 2026-10-04, TASK-P7-012.** `finops_ingest/collectors/digests.py` runs weekly, as
the `team_digests` row in `collector_schedule` with its reason, ADR-0012. It composes the
last complete week, Monday to Sunday in UTC, from `cost_focus_daily`, the rows the
allocation screen reads: one digest per team, grouped by the `team` tag with untagged spend
named as unallocated, and one executive digest for the whole payer, each with its top
services. Every figure is **measured** and cited, because a digest is an `Answer` and the
same rules hold: no numeral in the prose, and every value read from the rows with its
`as_of`. A first week makes no comparison, because there is no earlier week to compare
with.

The first cut is a deterministic template, `finops_query/digest.py`, so it calls no model,
and its estimated cost per run is recorded as zero, modelled. This differs from what was
known before the spec, which said written rather than templated.

A digest is stored whether or not anything can send it. `sent_at` stays null with its
reason, because where a digest goes is OPEN-11, and the screen says composed and not sent.
A rerun for the same week deletes that week's unsent digests and composes them again.

## Failure behaviour

One team failing does not fail the run. That team's failure is a SchemaDrift `sync_error`
under its own scope key, `digests:` followed by the audience and the team, the other
digests are written, and a later success clears it.

## Security considerations

Digests are payer wide under the guard, so only a person with a global scope sees them,
and the screen's coverage says so to anybody else. Confining a team's digest to that team
needs a mapping from a team tag to a scope, and nothing holds one yet. No personal data.

## Interface

`GET /assistant/digests` and the `/assistant/digests` screen.

## Not doing

**Sending.** A sender is an adapter behind a port once OPEN-11 is answered. **A model
written summary** in this cut. **A comparison across more than two weeks.**
