# FEAT-012: Query cost model

| Field | Value |
| --- | --- |
| Sub project | P2 |
| Status | Specified |
| Specification | [P2 spec](../specs/2026-08-23-p2-query-cost-governance-design.md) |
| Tasks | Not planned |
| Refresh cadence | 6 hours |

## What it does

Models the monthly cost of every dashboard panel and alert rule query from its refresh interval, its time window, and the ingestion rate of the log groups it reads.

## Why it exists

Ranking queries by cost is what turns a list of dashboards into an action.

## How it works

Models monthly cost per query from its refresh interval, its time window and the ingestion rate of the log groups it reads. Logs Insights is billed per gigabyte scanned, so scan per run is modelled from ingest rate times window. Metric engines are billed per metric requested per call. Panels run only while a dashboard is open, so runs per day uses a configured viewing hours assumption, while alert rules run continuously on their own schedule.

Since TASK-P8-013, 2026-10-06, the findings screen draws what each dashboard's queries cost a
month and a trend of what every audited query cost each day. The trend sums every query audited
on a day rather than today's queries only, so a dashboard deleted after a fix leaves its earlier
days behind and the fall shows. A day is measured only when every query that day was measured.

## What is already known

Prototype models Logs Insights as gigabytes scanned, and metric engines as metrics requested per call. Panels run only while a dashboard is open, so runs per day uses an assumed viewing hours figure. Alert queries run continuously. Every figure is labelled modelled until FEAT-018 calibrates it.

## Failure behaviour

A log group whose ingestion rate cannot be read produces a finding with no cost rather than a finding with a zero cost. The distinction is the whole point: zero means free, absent means unknown.

## Security considerations

No credential handling. Reads only metadata already collected.

## Interface

Writes `query_finding` with `provenance` set to `modelled`. A database constraint prevents a modelled row from carrying a measured run count. See [P2 spec](../specs/2026-08-23-p2-query-cost-governance-design.md) section 5.

Read over HTTP since TASK-P2-021. `GET /api/v1/query/findings` returns every finding ranked by monthly cost, ordered in the database because `ix_query_finding__cost` exists for it and sorting in the route would order the page rather than the estate. `GET /api/v1/query/findings/{finding_id}` adds the query as written, what it runs against, and `rate_usd_per_gib`, the published price, so the working on the screen has no constant a reader cannot check. `accuracy_percent` is null until FEAT-018 publishes one, and is never invented to make the screen look finished.

`scope_coverage` on these routes counts workspaces read over workspaces the tenant has, not findings over accounts. A findings list drawn from two of three workspaces is missing an unknown number of rows, and the envelope says so.

`GET /api/v1/query/trend`, since 2026-10-06: one row per day for the last thirty days, with
`run_date`, `cost_month_usd`, `queries`, `provenance`, `as_of` and `collected_at`. The envelope
is dated by the newest day, because the oldest is thirty days old by design.

## Not doing

Does not claim accuracy. Every figure is labelled `modelled` and carries a visible caveat until FEAT-018 publishes a back tested accuracy percentage.
