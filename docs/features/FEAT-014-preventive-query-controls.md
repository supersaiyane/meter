# FEAT-014: Preventive query controls

| Field | Value |
| --- | --- |
| Sub project | P2 |
| Status | Specified |
| Specification | [P2 spec](../specs/2026-08-23-p2-query-cost-governance-design.md) |
| Tasks | Not planned |
| Refresh cadence | On save, and in CI |

## What it does

Stops a cost generating dashboard from being saved at all: a workspace level minimum refresh interval, and a pipeline gate that rejects dashboard JSON combining a sub minute refresh with a window longer than 24 hours on a Logs Insights panel.

## Why it exists

ISS-020. A report of money already burned is a post mortem. The workspace refresh floor is free, needs no code, and removes most of the exposure on its own.

## How it works

Two mechanisms. The workspace level `min_refresh_interval`, which Grafana itself then enforces on every save, forever, with no code from us. And a continuous integration gate rejecting dashboard JSON that combines a sub minute refresh with a window longer than 24 hours on a Logs Insights panel.

## What is already known

Amazon Managed Grafana supports `min_refresh_interval` natively and Grafana enforces it. The CI gate applies to dashboards managed as code.

## Failure behaviour

A workspace where the floor cannot be set is reported as such. The CI gate fails the pipeline, which is the intended behaviour rather than a failure mode.

## Security considerations

Setting the workspace floor is a write, gated behind `query_write_level` at `workspace_floor` or above, defaulting to `none`. It is the smallest possible write surface: one setting, no dashboard touched.

## Interface

`POST /api/v1/query/remediate/{id}` at `WORKSPACE_FLOOR` kind. Recorded in `remediation_change` with a `before` value, so it is undoable. See [P2 spec](../specs/2026-08-23-p2-query-cost-governance-design.md) section 7.3.

## Not doing

Does not rewrite dashboards, that is FEAT-017. The CI gate only reaches dashboards managed as code, and how many that is remains ISS-096.
