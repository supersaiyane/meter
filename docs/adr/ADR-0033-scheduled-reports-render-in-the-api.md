# ADR-0033: Scheduled reports render inside the API, as each recipient

Date: 2026-10-07
Status: Accepted
Supersedes: nothing
Relates to: ADR-0009 (the HTTP API is the single enforcement point), ADR-0012 (cadence is data),
ADR-0029 and constraint 3

## Context

A schedule renders a saved view once for each of its recipients, in that recipient's scope, P8
spec section 5.7. The spec says what a run must do and not which process does it.

Everything a render needs lives in the API: the scope dependency that resolves a person's
access, the repository guard that confines a read, and the export responder that writes the file
and its record. The layering puts the ingest worker below the API, and nothing below the API may
import it, so a collector in the worker cannot render. Moving the guard and the responder down
would give the product two places that decide who may read what, which is how an authorization
bug is made, ADR-0009.

A screen and a route are also not the same thing. A saved view names a screen; a file is made
from a route. Only the screen knows which routes it reads, so the route a schedule renders has to
come from the screen.

## Decision

**The schedules render inside the API process, on a thread its lifespan starts and stops, as
each recipient.** For each recipient the runner resolves their scope as a request of theirs would
be resolved, mints a session for that one call, and calls the schedule's route in process with
`format` set. The same dependency, guard and responder make the file and write its record as if
the person had pressed Export, so a schedule cannot carry a row to someone who could not open it.
The session never leaves the process.

Its cadence is the `report_schedules` row in `collector_schedule`, ADR-0012, with a new column,
`runs_in`, saying the API runs it, so the ingest worker's due list leaves it out. Each look claims
the tenant's current slot in the run ledger, so two API containers render it once, and the
freshness screen shows the runner beside every collector. Each due schedule is taken in a
transaction of its own with SKIP LOCKED.

**A schedule names a saved view and one route its screen exports,** chosen in the browser from
that screen's own Export list, and the API refuses a route that answers no export.

**A kept file is handed back only while the reader's access still covers it.** A file made under
a wider scope than its reader now holds is refused, rather than handed over as rows they can no
longer see.

## Alternatives considered

- **A collector in the ingest worker.** It cannot import the guard or the responder, and a second
  copy of either is the bug ADR-0009 exists to prevent.
- **A separate process from the API image**, as the MCP server is. Clean separation, at the price
  of a new service, task definition and role in the hub stack for one loop that the API's own
  process runs as well. It remains the move if rendering ever needs more than one thread's worth.
- **Rendering when the file is opened.** The file would describe the moment it was opened rather
  than the schedule's moment, and a sender would have nothing to send.

## What it costs

The API process does background work. A failure there is logged with its traceback and the
tenant's claim stays RUNNING until the ledger reclaims it, so a look is not lost, but nothing
pages anyone yet. The API's task role needs the data bucket, which it already holds for every
task.

## Why this is an ADR

It decides which process holds the power to act as a person, and moving it later means moving
the minting of sessions with it.

## Consequences

- `finops_api/exports/scheduled.py` holds the runner; `finops_api/main.py` starts it from
  `bootstrap` alone, so an application a test builds never renders on its own.
- `collector_schedule.runs_in`, migration 0029; `finops_ingest.registry.due_collectors` returns
  the worker's rows only.
- The export responder answers every file with `X-Meter-Run`, so the runner annotates the record
  the responder wrote rather than writing a second.
- `tests/api/test_report_schedules.py` asserts two recipients with different scopes get different
  files from one schedule, and that a kept file is refused once its reader's access narrows.
