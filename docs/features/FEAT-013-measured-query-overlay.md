# FEAT-013: Measured query overlay

| Field | Value |
| --- | --- |
| Sub project | P2 |
| Status | Specified |
| Specification | [P2 spec](../specs/2026-08-23-p2-query-cost-governance-design.md) |
| Tasks | Not planned |
| Refresh cadence | 6 hours |

## What it does

Overlays real execution counts and scanned bytes from CloudTrail and CloudWatch Logs query history onto the modelled figures, so a row is labelled measured rather than estimated where evidence exists.

## Why it exists

A modelled number ranks reliably but cannot be defended. A measured one can.

## How it works

Overlays real evidence onto the modelled figures. CloudTrail `StartQuery` events give actual execution counts and the principal that ran each query. `logs:DescribeQueries` gives recent query history. `GetMetricData` call counts give metric engine volume. Matching is by query fingerprint, which is the query text normalised with template variables removed.

## What is already known

Prototype already collects CloudTrail `StartQuery` events, `logs:DescribeQueries` history, and `GetMetricData` call counts, and matches them to panel queries by fingerprint.

## Failure behaviour

Absent measured evidence is not a failure. The row simply stays `modelled`, which is the honest state rather than a degraded one.

## Security considerations

Reads CloudTrail, which contains principal identifiers. Those are already within the caller's scope by construction, because the events come from accounts the caller can see.

## Interface

Promotes a `query_finding` from `modelled` to `measured` and populates `measured_runs`. A constraint requires that a measured row states how many runs it measured. See [P2 spec](../specs/2026-08-23-p2-query-cost-governance-design.md) section 5.

## Not doing

Does not replace the model. A measured row still needs the model for the periods it did not observe.
