# FEAT-067: Report export to Excel and CSV behind the scope guard, with an About sheet

| Field | Value |
| --- | --- |
| Sub project | P8 |
| Status | Planned |
| Specification | [P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), section 5.5 |
| Tasks | TASK-P8-009 |
| Refresh cadence | On demand, and on a schedule through FEAT-069 |

## What it does

Every list route a screen reads accepts `format=xlsx` or `format=csv`, and one export responder
writes the view's own rows on the server, never in the browser. A workbook holds a Data sheet,
with FOCUS display names as headers and typed numbers, and an About this export sheet giving
scope and coverage, filters, grouping, period, currency, cost metric, `as_of`, `collected_at`,
every typed failure in the view, and when it was made and by whom, so a failed account is a row
there and never a zero in the data. An Export menu on every screen replaces the old Export
screen's CSV.

## Why it exists

The owner said on 2026-10-05 that there is no report a person can take away as an Excel sheet,
and the audit the same day found one export, a cost CSV, whose screen refuses Excel in words.
FEAT-045, the showback export, is delivered by this mechanism rather than built again.

## What is already known

The export answers after the same scope dependency and repository guard as the screen, and
tests hold that its rows equal the screen's and that a narrower scope never sees a row outside
it. Tag values come from member accounts, so a cell that starts with `=`, `+`, `-`, `@`, a tab
or a carriage return is written as text. A workbook stops at a configured row limit below
Excel's sheet maximum, says so in its About sheet and offers CSV for the full set, and every
export is recorded as one `report_run` row. The writer is XlsxWriter, chosen over openpyxl for
its constant memory mode and admitted through `make dep-check`.

## Status of this document

Planned. The feature is specified in the
[P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), section 5.5, and planned
as TASK-P8-009 in the [P8 plan](../plans/P8-implementation-plan.md), both pending the owner's
approval. The sections a built feature carries, how it works, its failure behaviour, its
security considerations, its interface and what it does not do, are written when it is built.
Recording only what is decided is deliberate: a document that invents detail ahead of the
build is worse than a short one, because it will be believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P8.
