# FEAT-069: Scheduled reports rendered for each recipient

| Field | Value |
| --- | --- |
| Sub project | P8 |
| Status | Planned |
| Specification | [P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), section 5.7 |
| Tasks | TASK-P8-011 |
| Refresh cadence | Per schedule: daily, weekly, monthly or at month close |

## What it does

A schedule names a saved view, a format, XLSX or CSV, a cadence, and recipients who are Meter
principals. Each run renders once per recipient, in that recipient's scope, and stores the files
in the hub's data bucket under the tenant's prefix. A file is fetched through a Meter route that
checks scope again.

## Why it exists

The owner chose scheduled delivery on 2026-10-05 as one of the four reporting capabilities in
the first build. Rendering per recipient and fetching through a scope checked route is the whole
defence against a schedule becoming a scope leak, because a schedule then cannot carry a row to
someone who could not open it.

## What is already known

Delivery is a `ReportSender` port with a fake until OPEN-11 names email or Slack, and a run with
no sender is stored and listed as rendered and not sent, the shape digests already use. A
collector in `collector_schedule`, with its reason and its cost under ADR-0012, renders each due
schedule, and one recipient failing does not fail the run. No deletion job runs until OPEN-15 is
answered, and the screen says how long files are kept.

## Status of this document

Planned. The feature is specified in the
[P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), section 5.7, and planned
as TASK-P8-011 in the [P8 plan](../plans/P8-implementation-plan.md), both pending the owner's
approval. The sections a built feature carries, how it works, its failure behaviour, its
security considerations, its interface and what it does not do, are written when it is built.
Recording only what is decided is deliberate: a document that invents detail ahead of the
build is worse than a short one, because it will be believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P8.
