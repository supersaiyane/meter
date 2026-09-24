# FEAT-018: Cost model calibration

| Field | Value |
| --- | --- |
| Sub project | P2 |
| Status | Specified |
| Specification | [P2 spec](../specs/2026-08-23-p2-query-cost-governance-design.md) |
| Tasks | Not planned |
| Refresh cadence | Monthly |

## What it does

Back tests the modelled query cost against the actual CUR usage types for scanned bytes and metrics requested, and publishes the accuracy percentage inside the product.

## Why it exists

ISS-022 and ISS-032. This is what turns modelled from a disclaimer into a number an engineering director will act on.

## How it works

Back tests the modelled query cost against the actual bill, comparing the modelled monthly figure to the CUR usage types for scanned bytes and metrics requested over the same period, and publishes the resulting accuracy percentage inside the product.

## What is already known

Compares the modelled monthly figure against `*-DataScanned-Bytes` and `CW:MetricsRequested` in the billing data for the same period.

## Failure behaviour

Insufficient CUR history produces no accuracy figure rather than a misleading one. A published accuracy of an unknown quality is worse than an absent one.

## Security considerations

Reads P1 cost data, so it is scope filtered like everything else.

## Interface

`GET /api/v1/query/accuracy`, and the figure appears next to every modelled number in the interface. See [P2 spec](../specs/2026-08-23-p2-query-cost-governance-design.md) section 11.

## Not doing

Does not correct the model automatically. It measures the model, and a correction is a change someone makes having seen the measurement.
