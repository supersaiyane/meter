# FEAT-022: Allocation, showback and the unallocated bucket

| Field | Value |
| --- | --- |
| Sub project | P1 |
| Status | In build |
| Specification | [P1 spec](../specs/2026-09-18-p1-cost-intelligence-design.md) |
| Tasks | [P1 plan](../plans/P1-implementation-plan.md), TASK-P1-009 and TASK-P1-011 |
| Screen | `/cost/allocation` |

## What it does

Groups a period's charges by one tag key, and shows what carries no such tag as a
row of its own.

## Why it exists

Somebody has to own a charge before anything about it can change. The number that
matters most on this screen is the one nobody owns.

## How it works

The same rows as FEAT-021, grouped on a JSONB tag lookup rather than a column, so
the key cannot name a column even though it arrives from a request. Charges with
no value for the key fall into a literal `unallocated` bucket, which is ranked
and rendered like any other row.

## What is already known

Tags first. Cost Categories are a second source and adding one before the first
is proved makes a disagreement between them impossible to attribute.

## Failure behaviour

A tag key nothing carries is a true answer about an estate that does not use that
key, not an error and not an empty page: everything lands in `unallocated`. The
route refuses a request with no key at all, because there is no sensible default
and guessing one would group an estate by something nobody asked for.

## Security considerations

The same two scope points as FEAT-021, over the same table.

## Interface

`GET /cost/allocation?tag=<key>`, returning the meta envelope.

## Not doing

Showback as a file. That is FEAT-045 and the roadmap is right that finance is the
actual consumer, but an export of a surface still changing shape is one nobody
can rely on.

## Honestly

The unallocated row is the point. A view that quietly drops what it cannot
attribute reports a smaller estate than exists, and the gap between that number
and the invoice is the first thing finance finds. On the seeded estate it is 22
percent.
