# FEAT-086: The commitment inventory: every commitment's real term, end and payment

| Field | Value |
| --- | --- |
| Sub project | P14 |
| Status | Specified |
| Specification | [P14 spec](../specs/2026-10-13-p14-commitments-design.md), sections 5.3, 5.5, 5.8 and 6 |
| Tasks | TASK-P14-001, TASK-P14-002 and TASK-P14-003 |
| Decisions | OPEN-37, OPEN-39, ADR-0037 |
| Issues addressed | ISS-294, ISS-295 |
| Refresh cadence | Daily |

## What it does

Lists every Savings Plan and every reservation the organization holds, for EC2, RDS, ElastiCache, OpenSearch, Redshift and MemoryDB, with its owning account, Region, program, term, payment option, hourly commitment or quantity, start, end and state.

## Why it exists

FEAT-024 infers a commitment's term from the reporting window, so no renewal date Meter shows could be planned around. A renewal calendar, a ladder and a purchase plan all start from what is actually held and when it ends.

## How it works

Not built yet. The `commitment_inventory` collector reads each member account through its collector role: Savings Plans and the RDS, ElastiCache, OpenSearch, Redshift and MemoryDB reservations through the relay, ADR-0037, and EC2 reservations through the EC2 endpoint. It writes `commitment_inventory`, `PayerWide`, ADR-0025. TASK-P14-001 first makes the existing Cost Explorer reads run as the payer, ISS-294.

## Data sources and freshness

| Source | Cadence | Best possible freshness |
| --- | --- | --- |
| Each service's describe call | Daily | The day before |

## Measured or modelled

Measured: every field is the source's own.

## Failure behaviour

An account that refuses reads as its typed cause and keeps its last good rows with their age. DynamoDB reserved capacity has no read API and is listed as unreadable, ISS-295, never as none held.

## Security considerations

Read only. The relay's allow list and the member collector role gain only the describe calls, and a test fails the gate on any purchase, exchange or sale action. The inventory is visible at global scope only.

## Interface

`GET /v1/commitments/inventory`, and the inventory panel of the commitments screen.

## Not doing

Buying, exchanging, selling or queueing a commitment. DynamoDB reserved capacity, which no API reads.
