# FEAT-069: Scheduled reports rendered for each recipient

| Field | Value |
| --- | --- |
| Sub project | P8 |
| Status | Delivered |
| Specification | [P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), sections 5.7, 6 and 7 |
| Tasks | TASK-P8-011 |
| Refresh cadence | Per schedule: daily, weekly, monthly or at month close. The runner looks every fifteen minutes, its row in `collector_schedule` |

## What it does

A schedule names a saved view, one route the view's screen exports, a format, XLSX or CSV, a
cadence, and the Meter principals it renders for. Each run makes one file per recipient, within
that recipient's own access, keeps it in the hub's data bucket under the tenant's prefix, and
lists it for them on the Scheduled screen, where it is fetched through a route that checks their
access again. Schedule, in the Report Library, opens the view's own screen with the schedule
panel open. The Scheduled screen pauses, resumes and deletes schedules and lists the reports made
for the reader, the files they exported among them.

## Why it exists

The owner chose scheduled delivery on 2026-10-05 as one of the four reporting capabilities in
the first build. Rendering per recipient and fetching through a scope checked route is the whole
defence against a schedule becoming a scope leak: a schedule cannot carry a row to someone who
could not open it.

## How it works

`report_schedule`, migration 0029, holds the owner, the view, the route, the format, the
cadence, the recipients, whether it is enabled and its next run. A trigger holds that the view is
one the owner can open, the one invariant a check cannot express, and a schedule is its owner's
alone under `ByPrincipal`, ADR-0029.

The runner lives in the API, ADR-0033, because the scope dependency, the guard and the export
responder are there and nothing below the API may import them. On its cadence it claims each
tenant's slot in the run ledger, takes each due schedule in its own transaction with SKIP LOCKED,
and for each recipient resolves their scope, mints a session for one call and calls the
schedule's route in process with `format` set. The responder makes the file and its `report_run`
row as for any export and answers with the row's identifier; the runner keeps the file under
`reports/<tenant>/<run>.<format>` and marks the row RENDERED. A recipient whose render fails gets
a FAILED row with its typed cause and the rest carry on, and the ledger records the look as
PARTIAL. The next run is the cadence's next time after the look, from
`finops_core/domain/report_schedule.py`.

A schedule's route comes from the view's own screen: the panel offers the routes the screen
offers for export, and the API refuses a path that answers no export.

## Failure behaviour

A view its owner can no longer open renders nothing: each recipient gets a FAILED row saying so,
once, and the schedule pauses. A deleted view leaves its schedules in place with no view, paused
the same way, rather than deleting other people's schedules with it. A recipient the identity provider does not know, or whose access reaches no account, gets
AccessDenied. A route that refuses gets the cause its status names; a store that cannot be
reached gets Unreachable and keeps no file; a sender that fails gets its own cause and the file
is kept, so the recipient can still fetch it. A look that fails outright is logged with its
traceback, and its claim stays RUNNING until the ledger reclaims it. Without a bucket nothing
renders: the schedules route says `rendering: false`, the Scheduled screen says so in words, and
the file route answers 503.

## Security considerations

A file is made by the same dependency, guard and responder as an Export press, as its recipient,
so its rows are the rows the recipient could read at that moment. The session minted for the call
never leaves the process. A kept file is handed back only to the person it was made for, and only
while their access still covers every account it was made under: a reader whose access has
narrowed is refused with a sentence saying why, and the schedule's next run makes the file again
within the access they hold then. A schedule names people and never accounts; its owner sees the
recipients they named, and a recipient sees their own runs and never the schedule.
`report_schedule` holds people's identifiers and is classified personal. No retention job reads
it and `erase_principal` does not reach it, ISS-256.

## Interface

- `GET /api/v1/reports/schedules`: the reader's schedules, with `rendering`, `retention` and
  `delivery` said by the server.
- `POST /api/v1/reports/schedules`: `view_id`, `export_path`, `format`, `cadence` and
  `recipients`. Answers 201.
- `PATCH /api/v1/reports/schedules/{schedule_id}`: `enabled`, `format`, `cadence` or
  `recipients`. A changed cadence, or a schedule resumed, runs next at its next time from now.
- `DELETE /api/v1/reports/schedules/{schedule_id}`: the runs it made stay with their readers.
- `GET /api/v1/reports/runs`: the reader's runs, the latest first, their exports included.
- `GET /api/v1/reports/runs/{run_id}/file`: a kept file, after the scope check.

`METER_S3_BUCKET` names the data bucket. The hub stack passes it to every task, empty turns
rendering off, and `make up` makes it in LocalStack.

## Not doing

Nothing is sent: OPEN-11 decides between email and Slack, and until then a run is kept and listed
as made and not sent. Nothing deletes a file or a run: OPEN-15 decides how long they are kept, and
the screen says so. A schedule renders one route of its view's screen, not every panel on it, and
a filter a screen applies in the browser rather than in its route's query is not in the file, as
with Export.
