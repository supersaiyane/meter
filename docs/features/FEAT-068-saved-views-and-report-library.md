# FEAT-068: Saved views and a report library, shared as configuration

| Field | Value |
| --- | --- |
| Sub project | P8 |
| Status | Planned |
| Specification | [P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), section 5.6 |
| Tasks | TASK-P8-010, after TASK-P8-003 puts filters in the query string |

## What it does

A person saves a view, names it, and keeps it private or shares it with the tenant. A saved
view stores a screen and its query string and nothing it rendered, so opening one renders it in
the opener's scope. The Report Library opens, renames, duplicates, shares, deletes and exports
saved views.

## Why it exists

The owner chose saved views and a report library on 2026-10-05 as one of the four reporting
capabilities in the first build. Because a view is configuration and never data, sharing a view
shares a question, not an answer.

## What is already known

It needs filters to live in the query string, as `docs/13-UI-ARCHITECTURE.md` already says they
do and the code does not, ISS-235, which TASK-P8-003 closes. The `saved_view` table's
constraints require a screen path the navigation knows, a name that is not blank and a query
that is a JSON object, and its visibility is PRIVATE or SHARED. A private view is confined to
its owner under ADR-0029, and rendering in the opener's scope is asserted with two principals.

## Status of this document

Planned. The feature is specified in the
[P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), section 5.6, and planned
as TASK-P8-010 in the [P8 plan](../plans/P8-implementation-plan.md), both pending the owner's
approval. The sections a built feature carries, how it works, its failure behaviour, its
security considerations, its interface and what it does not do, are written when it is built.
Recording only what is decided is deliberate: a document that invents detail ahead of the
build is worse than a short one, because it will be believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P8.
