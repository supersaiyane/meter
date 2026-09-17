# Runbook: restore the database

**When.** After data loss, after a bad migration, or on the schedule that keeps
this runbook honest. Run the drill at least once per release that touches
`migrations/`.

**Why a runbook and not a note.** A restore that has never been tested is a
hypothesis. The hypothesis is not "does the snapshot exist", because snapshots
almost always exist. What fails is everything after: a schema the migrations
will not apply on top of, an application that will not start against the
restored settings, or a freshness screen reporting day old data as current to
somebody deciding what to do next.

## The drill

```bash
make restore-drill
```

It creates a scratch database, restores a copy into it, runs the migrations to
head, starts the application against it, and reads `/healthz`. It drops the
scratch database afterwards unless you pass `--keep`.

It refuses any database that is not local before it opens a connection. That
guard is the only part of the script that matters if the rest is forgotten.

A result of `degraded` from `/healthz` is **correct, not a failure**. Restored
data is as old as the copy it came from, and an application calling it current
would be the defect this drill exists to catch.

## The real thing

Four steps. Only the first differs from the drill.

1. **Produce a copy.** Against Aurora, `RestoreDBClusterFromSnapshot` into a new
   cluster. Never restore over the live one: a restore that overwrites its own
   source cannot be undone if the snapshot turns out to be the problem.
2. **Restore into a scratch database.** The drill does this with plain SQL over
   the same driver the application uses, so no client tooling is needed on the
   machine running it.
3. **Run the migrations to head.** This is the step that catches a snapshot
   taken before a migration nobody remembers. Do not skip it because the schema
   "looks right".
4. **Start the application and read the freshness screen.** The rows being back
   is not the finish line. The finish line is the screen that says how old they
   are telling the truth, because that is what an operator reads first.

Point the drill at a real snapshot with:

```bash
make restore-drill DUMP=/path/to/snapshot.sql
```

## What has actually been proven

Steps 2, 3 and 4 have been performed against a real restore of a real local
database, including the migrations reaching head and the application starting
and reporting. Step 1 from an Aurora snapshot has never run, because no AWS
account has ever been provisioned. That is ISS-111, and it is now the only
untested link rather than the whole chain.

## If it fails

| Symptom | Cause | Action |
| --- | --- | --- |
| The restore stops at a statement | The copy is truncated or from a different major version | Take a fresh copy. Do not edit the dump |
| `alembic upgrade` fails | The snapshot predates a migration that is not backward compatible | Constraint 12 says this should be impossible. If it happens, the migration that broke it is the bug, not the restore |
| The application starts and `database_reachable` is false | The scratch database exists and the schema did not restore | Check the restore output for the first failing statement |
| `/healthz` reports `degraded` | Normal. The data is as old as the copy | Nothing. See above |
