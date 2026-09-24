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

## What is already known

Prototype models Logs Insights as gigabytes scanned, and metric engines as metrics requested per call. Panels run only while a dashboard is open, so runs per day uses an assumed viewing hours figure. Alert queries run continuously. Every figure is labelled modelled until FEAT-018 calibrates it.

## Failure behaviour

A log group whose ingestion rate cannot be read produces a finding with no cost rather than a finding with a zero cost. The distinction is the whole point: zero means free, absent means unknown.

## Security considerations

No credential handling. Reads only metadata already collected.

## Interface

Writes `query_finding` with `provenance` set to `modelled`. A database constraint prevents a modelled row from carrying a measured run count. See [P2 spec](../specs/2026-08-23-p2-query-cost-governance-design.md) section 5.

## Not doing

Does not claim accuracy. Every figure is labelled `modelled` and carries a visible caveat until FEAT-018 publishes a back tested accuracy percentage.
