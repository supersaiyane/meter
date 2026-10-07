# FEAT-068: Saved views and a report library, shared as configuration

| Field | Value |
| --- | --- |
| Sub project | P8 |
| Status | Delivered |
| Specification | [P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), sections 5.6, 6 and 7 |
| Tasks | TASK-P8-010 |
| Refresh cadence | None. A view is read when it is opened and holds no figure to refresh |

## What it does

Save view, beside Export on every built screen and tab, keeps the screen and its query string
under a name, for the reader alone or shared with everyone in the organization. The Report
Library, under Report, lists the reader's own views and every shared one, the latest changed
first, and opens, renames, duplicates, shares, makes private, deletes and exports them. A view
stores a screen and its query and nothing it rendered, so opening one reads the screen afresh in
the opener's own scope.

## Why it exists

The owner chose saved views and a report library on 2026-10-05 as one of the four reporting
capabilities in the first build. Because a view is configuration and never data, sharing a view
shares a question, not an answer: a colleague narrowed to two accounts who opens a view saved by
a reader of the whole estate sees their two accounts.

## How it works

`saved_view`, migration 0028, holds the tenant, the owner, the name, the screen path, the query
as a JSON object, the visibility and two timestamps. The screen path must be one the navigation
knows. `finops_api/screens.py` lists the screens and tabs of `finops-web/src/shell/sections.ts`,
`tests/api/test_screens.py` fails when the two disagree, and the migration copies the list into
the table's constraint, which `tests/api/test_saved_views.py` reads back out of the database.

The guard reads the table through `OwnedOrShared`, ADR-0032: a view is read by its owner, and by
everyone in the tenant once shared, and a global scope does not widen it to a colleague's
private view. The repository's writes carry the owner as well as the scope, so only the owner
renames, shares or deletes a view, and each write is audited, ALLOWED or DENIED.

The browser keeps the query as the address holds it: a parameter given once is its value, and
one given more than once is every value in order. Open goes back to that address through the
link wrapper, so an account chosen in the address is kept unless the view names its own,
FEAT-075. Duplicate saves a private copy of any view the reader can open, named as a copy.
Export opens the view with its Export menu already open, because a library row has no rows of
its own.

## Failure behaviour

A view somebody else keeps private is not found, 404, whether or not it exists, as a resource
outside a reader's scope is not found. A shared view the reader did not save is found, and a
change to it is refused, 403, with a sentence saying who may change it and that a copy is one
Duplicate away. A refusal is answered rather than raised, because the request's transaction
would otherwise roll back the DENIED audit row with it.

A name that is blank, more than one line or longer than the database keeps, a screen the
navigation does not know, a query past its bounds, and a change that names nothing or reaches
for the screen or the query, are refused with 422 before the database, which refuses the same
rows again if the API did not. The library says a failed read as a failure, never as an empty
library, and says in words what a refused change was refused for.

## Security considerations

A shared view crosses every account boundary in the tenant, which is safe only because it holds
configuration: no column of `saved_view` carries a figure. A shared view does not tell the people
it is shared with who saved it, and the answer says only whether the reader owns it. Scope is
enforced twice, by `get_scope` and the guard, and the writes add the owner to the guard's
predicate, constraint 3. The table holds a person's identifier and the names they chose, and is
classified personal in `docs/09-DATA-CLASSIFICATION.md`. No retention job reads it and
`erase_principal` does not reach it, ISS-255.

## Interface

- `GET /api/v1/reports/views`: the reader's views and the shared ones, the latest changed
  first, cut at a limit, with the coverage saying when there are more.
- `POST /api/v1/reports/views`: `name`, `screen_path`, `query` and `visibility`, private unless
  shared is asked for. Answers 201 with the view.
- `GET /api/v1/reports/views/{view_id}`: one view.
- `PATCH /api/v1/reports/views/{view_id}`: a new `name`, a new `visibility`, or both. The
  owner's alone.
- `DELETE /api/v1/reports/views/{view_id}`: answers with the view as it was. The owner's alone.

Each answers in the envelope, its `as_of` and `collected_at` the moment the library was read,
and its coverage counted in saved views. The routes are exempt from export in
`tests/api/test_export_routes.py`, because a view exports from its own screen.

## Not doing

A view cannot be pointed at another screen or query; that is a new view, saved anew. A shared
view is shared with the whole tenant and nobody narrower. The library does not list a person's
export records; the Scheduled screen does, FEAT-069, and whether the library should as well is
OPEN-19. Schedule, on each row, opens the view's own screen with the schedule panel open.
