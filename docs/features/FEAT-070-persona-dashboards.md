# FEAT-070: Persona dashboards for executive, FinOps practitioner and engineering lead

| Field | Value |
| --- | --- |
| Sub project | P8 |
| Status | Planned |
| Specification | [P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), section 5.8 |
| Tasks | TASK-P8-012 |

## What it does

The Overview opens on the dashboard for the reader's persona, executive, FinOps practitioner or
engineering lead, offers the other two, and remembers the reader's last choice. Every KPI names
its formula and baseline where it is shown, and every figure links to the screen that owns it.

## Why it exists

The owner said on 2026-10-05 that there is no graphical dashboard, and chose persona dashboards
as one of the four reporting capabilities in the first build. Each persona reads different
figures: an executive reads effective cost against budget and forecast, a practitioner reads
commitment coverage and unallocated cost, and an engineering lead reads cost, anomalies and
rightsizing in the team's scope.

## What is already known

It is built from existing routes only and adds no new number. Effective savings rate is the KPI
library's, one minus actual spend with discounts over equivalent spend at the on demand rate,
and the tile says on demand equivalent, because FOCUS, Azure and Cloudability each use a
different baseline. A KPI the data cannot support yet says so and shows no figure, never zero.

## Status of this document

Planned. The feature is specified in the
[P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), section 5.8, and planned
as TASK-P8-012 in the [P8 plan](../plans/P8-implementation-plan.md), both pending the owner's
approval. The sections a built feature carries, how it works, its failure behaviour, its
security considerations, its interface and what it does not do, are written when it is built.
Recording only what is decided is deliberate: a document that invents detail ahead of the
build is worse than a short one, because it will be believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P8.
