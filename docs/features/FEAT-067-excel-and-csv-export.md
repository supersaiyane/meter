# FEAT-067: Report export to Excel and CSV behind the scope guard, with an About sheet

| Field | Value |
| --- | --- |
| Sub project | P8 |
| Status | Delivered |
| Specification | [P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), section 5.5 |
| Tasks | TASK-P8-009 |
| Refresh cadence | On demand, and on a schedule through FEAT-069 |

## What it does

Every list route a screen reads answers `format=xlsx` with a workbook and `format=csv` with a
CSV, written on the server from the route's own rows and never assembled in the browser. A
workbook holds a Data sheet, with FOCUS display names as headings and typed numbers, and an
About this export sheet giving the view, filters, grouping, period, currency, cost metric,
scope, coverage, `as_of`, `collected_at`, the row count and the row limit, when it was made
and by whom, and every typed failure in the view as a row of its own, so a failed account is a
row there and never a zero in the data. An Export menu beside every screen's title offers each
view the screen reads as either file. FEAT-045, the showback export, is delivered by this
mechanism rather than built again.

## Why it exists

The owner said on 2026-10-05 that there is no report a person can take away as an Excel sheet,
and the audit the same day found one export, a cost CSV, whose screen refused Excel in words.

## How it works

**One responder, applied to the whole route.** `@exportable(ExportSpec(...))` sits between a
route's `@router.get` and its `def`, from `finops_api/exports/responder.py`. Without `format`,
or with `format=json`, the route answers as it always has. With a file format, the envelope
the route built after the scope dependency and the repository guard is written as a file and
returned in its place. There is no second query, so the file's rows are the screen's rows by
construction rather than by a test that has to catch a drift. A decorator rather than a line
in each route, because a route can return from more than one place, and an export added at the
last `return` would answer JSON for a file from an early one.

**The rows.** Each route's spec names its row model and where the rows are in its envelope.
`finops_api/exports/cells.py` flattens a row: a nested model's fields become columns of their
own, a list inside a row is not a cell and is left out, and a column is headed by the route's
own name for it, its FOCUS display name, or its own words, in that order.

**The two files.** `finops_api/exports/writers.py`. The workbook is XlsxWriter in constant
memory mode, a row at a time through a temporary file, so a hundred thousand rows cost one
row's memory. Money and counts are numbers, so a column sums in the spreadsheet; days are
days; times are converted to UTC and the About sheet says so. The CSV is UTF-8 with a byte
order mark, every row, with times carrying their offset.

**The record.** One `report_run` row per file, written in the transaction of the read: who,
which view and query, which scope as its account list, the format, rows, bytes, and whether a
workbook stopped at the row limit. Migration `0026_report_run`, with every invariant a check
constraint, see `docs/07-DATA-MODEL.md`.

**The browser.** The query hooks offer each view they read to the shell, from
`finops-web/src/api/exportViews.ts`, and only from inside a screen, so a figure the shell reads
for itself is never offered. `finops-web/src/shell/ExportMenu.tsx` asks the server for the
view's own path with the format added and saves the server's file under the server's name.

## What the exports hold

34 routes export, held by `tests/api/test_export_routes.py`, which fails for any GET route that
neither exports nor is named with the reason it does not. The nine that do not are a graph
walk, a blast radius, the coverage banner, the map's starting points, the reader's own session
and four detail pages of one item.

A route whose screen shows more than one table exports its first and says so in the About
sheet's Note: commitments export their use, quotas their measurable ones, and the forecast its
months, ISS-247. The resource list exports the page the screen asked for, and its Note gives
the rows and the total. Cost Explorer exports the rows it shows, and its Note gives the groups
past its row limit and what they cost together.

## Failure behaviour

A format other than `json`, `xlsx` or `csv` is refused with 422. A route that refuses, a 404
for a tenant with no period collected, refuses the file the same way rather than sending an
empty one. A session that names no person is refused a file with 403, because every file is
recorded against a person, and the screen still answers it. A workbook past the row limit
stops, says so on its About sheet with the full count, and points at the CSV, which holds
every row. The menu says in words why a download failed, and a browser that cannot save a file
a page made gets a sentence rather than a button that does nothing.

## Security considerations

The file is the route's own envelope, built after `get_scope` and the repository guard, so an
export cannot reach a row the screen could not. `tests/api/test_export_parity.py` holds that
against a database: the file's rows equal the screen's, a narrower reader's files hold only
its accounts, and every file writes one record.

A tag value comes from a member account, and one starting with `=` is a formula to a
spreadsheet. In the workbook every text cell is written as a string, with the string to
formula, string to number and string to URL conversions off. In the CSV a text cell starting
with `=`, `+`, `-`, `@`, a tab or a carriage return is led by an apostrophe. Both are tested for
each character, and a negative number stays a number.

Every file is answered with `Cache-Control: no-store`, and each `report_run` row is confined to
its person by the guard's `ByPrincipal` rule, ADR-0029. No retention job reads the record yet
and `erase_principal` does not reach it, ISS-249.

## Interface

`GET <route>?format=xlsx` or `?format=csv` on any exporting route, with the route's own query.
The file is named `meter-<view>-<YYYY-MM-DD>.<xlsx|csv>`. `METER_EXPORT_ROW_LIMIT` sets the
workbook's row limit, 100,000 in `.env.example`, at most 1,048,575, the sheet maximum less its
heading row. The hub's task definition does not pass it yet, nor 67 other settings the API
requires, ISS-250. The Export menu is beside the title of every screen that reads an exporting view,
and absent from a screen that reads none.

Every file answers with `X-Meter-Run`, the record it was written as, and the record keeps the
file's `as_of` and `collected_at`, so the report runner can find the row a file made, FEAT-069.

## Not doing

A CSV has no About sheet. It holds every row and nothing else, and the workbook is the file
that says what it is. The showback CSV carries its period, timestamps and coverage on every
row, FEAT-045. Exports to a schedule are FEAT-069, and the Scheduled screen lists a person's
records; whether the report library should as well is OPEN-19.
