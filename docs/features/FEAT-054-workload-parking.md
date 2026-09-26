# FEAT-054: The hours nothing runs, as a finding

| Field | Value |
| --- | --- |
| Sub project | P3 |
| Status | Delivered |
| Specification | [competitive review](../11-COMPETITIVE-REVIEW.md), 2026-09-26 candidate list |
| Tasks | `TASK-P3-021` |
| Refresh cadence | Daily. A schedule shape does not change hourly, ADR-0012 |
| Source | Adopted from the IBM Turbonomic review on 2026-09-26 |

## What it does

Reads hourly utilization over fourteen days, folds it into a one hundred and sixty eight
hour week, and finds the contiguous hours in which every observed week was idle. The finding
names the window, in the reader's own terms, and what stopping during it would save.

A finding, not a schedule. Meter is read only in v1, constraint 6.

## Why it exists

It is the largest untouched saving in most estates, and it is invisible to every rule we
have. `IDLE_INSTANCE` says nothing ever uses this, so delete it. Parking says something uses
this every weekday and nothing uses it at night, so keep it and stop paying for the nights.
A resource that is busy at noon passes every existing check.

## How it works

`read_many` with `period_seconds=3600`, so the adapter batches and
`METER_GETMETRICDATA_BATCH_SIZE` is honoured. Hours are folded by their position in the week
and an hour is idle only when every observed week was idle in it.

An hour with no data point is **not** an idle hour. A resource that is already stopped
publishes nothing, so treating absence as idle would recommend parking a window in which the
resource is already parked.

## Failure behaviour

Fewer than two full observed weeks produces **no finding at all**, rather than a finding with
low confidence. One week holds exactly one of each weekday, so a bank holiday, a deployment
freeze or a monthly batch job all read as the normal shape of the week. A confidence band on a
claim about somebody's production schedule is not a warning anybody acts on.

`NoData` across the whole window is a typed cause, never a zero.

## Security considerations

Read only. No schedule is created and no stop is issued, constraint 6. The metric read is
through the existing scoped session, so a narrowed reader sees findings only for accounts they
can read.

## Interface

`/waste`, in the same list as every other finding, with a lifecycle and an owner. The saving
renders as modelled through `Figure`. The rationale names the hours and the day range, never a
raw hour index, and states which part of the cost is not saved, because a parked resource
still holds its storage.

The risk verdict is reversible and disturbs running work, so it is never a no regret change.
Parking is a stop and a start.

## Not doing

The schedule. The review's phrasing is a finding first and a schedule later, and the later
half needs a write path we do not have. FEAT-040 is how one would ever be authored.

Excluding resources a tag says are production. That needs a tag convention we do not enforce,
and inventing one inside a collector puts a policy decision in the wrong layer.
