# FEAT-011: Grafana workspace scanner

| Field | Value |
| --- | --- |
| Sub project | P2 |
| Status | Specified |
| Specification | [P2 spec](../specs/2026-08-23-p2-query-cost-governance-design.md) |
| Tasks | Not planned |
| Refresh cadence | 6 hours, see ADR-0012 |

## What it does

Walks every Amazon Managed Grafana workspace, dashboard, panel and alert rule across accounts and regions, extracts each query, and classifies its engine.

## Why it exists

The failure that started this project was invisible. Nobody knew which dashboard was running which query at what refresh over what window.

## How it works

One `QuerySurface` port with three connection strategies below it, because the three Grafana variants share about 90 percent of their logic and differ only in how you find them and how you authenticate. `AmgConnection` discovers via `grafana:ListWorkspaces` and mints a temporary service account token per run. `SelfHostedConnection` has no discovery API at all, so it reads the `grafana_instance` table. `CloudConnection` reads the same table, one row per Grafana Cloud stack. Each surface is walked for dashboards, panels and Grafana managed alert rules.

## What is already known

A working prototype exists, `sample_lambda.py`, 2,740 lines. It already does workspace discovery, token minting, dashboard and alert walking, and engine classification across Logs Insights, CloudWatch metric search, Metric Insights SQL and PromQL. Productionizing means decomposing it against the 800 line ceiling, adding tests, and moving history into the warehouse. ISS-023, ISS-026, ISS-027.

## Failure behaviour

An instance Meter cannot reach is listed and **marked unreachable**, and its queries are excluded from every total with the exclusion stated. Silently omitting it would produce a confident organization total wrong by an unknown amount. A dashboard shape the parser does not recognise raises `SchemaDrift` rather than being skipped.

## Security considerations

Read only against Grafana at this feature. Credentials are Secrets Manager references, never values, and the temporary AMG token is revoked at the end of each run. Grafana Cloud introduces a third party credential into Meter, which is ISS-091 and needs a threat model row.

## Interface

Feeds `query_definition`. Surfaced through `GET /api/v1/query/instances`. See [P2 spec](../specs/2026-08-23-p2-query-cost-governance-design.md) sections 4.1 and 5.

## Not doing

Does not model cost, that is FEAT-012. Does not scan QuickSight, Athena, Redshift or OpenSearch, that is FEAT-019, which the port naming makes an addition rather than a redesign.
